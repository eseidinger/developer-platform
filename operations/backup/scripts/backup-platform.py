#!/usr/bin/env python3
"""Capture, verify and retain one platform recovery bundle. Run via systemd as root."""
import argparse
from contextlib import contextmanager
import selectors
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid


class BackupError(Exception):
    pass


def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class Job:
    def __init__(self, config):
        self.config = config
        self.root = Path(config['platform_dir'])
        self.state = Path(config.get('state_dir', '/var/lib/developer-platform-backup'))
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.restic = config.get('restic', '/usr/local/sbin/platform-restic')
        self.docker = config.get('docker', '/usr/bin/docker')
        self.stage = 'starting'

    def read(self, name, default):
        path = self.state / name
        return json.loads(path.read_text()) if path.exists() else default

    def command(self, args, **kwargs):
        # Never send command diagnostics (possibly secrets) to journal or notifications.
        result = subprocess.run(args, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                check=False, **kwargs)
        if result.returncode:
            raise BackupError('command failed')
        return result.stdout

    def compose(self, *args):
        return self.command([self.docker, 'compose', *args], cwd=self.root)

    def notify(self, payload):
        url = self.config['watchdog_url']
        if not url.startswith('https://'):
            raise BackupError('HTTPS watchdog required')
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + self.config['watchdog_token'],
                     'Content-Type': 'application/json'})
        # Credentials must never follow redirects to another endpoint.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            if response.status != 204:
                raise BackupError('notification rejected')

    def queue(self, payload):
        atomic_json(self.state / 'notification.json', payload)
        return self.retry_notification()

    def retry_notification(self):
        path = self.state / 'notification.json'
        if not path.exists():
            return True
        try:
            self.notify(json.loads(path.read_text()))
        except Exception:
            print('Backup signal delivery failed; pending retry.', file=sys.stderr)
            return False
        path.unlink()
        return True

    def resume(self):
        path = self.state / 'resume.json'
        if path.exists():
            failed = False
            for container in json.loads(path.read_text()):
                try:
                    self.command([self.docker, 'start', container], timeout=90)
                except Exception:
                    failed = True
            if failed:
                raise BackupError('service restart failed; recovery intent retained')
            path.unlink()

    def volume_state(self, bundle, services):
        containers = []
        mounts = []
        for service, targets in services:
            ids = self.compose('ps', '-q', service).decode().split()
            if len(ids) != 1:
                raise BackupError('required service unavailable')
            info = json.loads(self.command([self.docker, 'inspect', ids[0]]))[0]
            if not info['State']['Running']:
                raise BackupError('required service not running')
            containers.append(ids[0])
            for target in targets:
                found = [m for m in info['Mounts'] if m['Destination'] == target and m['Type'] == 'volume']
                if len(found) != 1:
                    raise BackupError('expected named volume missing')
                mounts.append((service + '-' + target.rsplit('/', 1)[-1], Path(found[0]['Source'])))
        # Write recovery intent BEFORE stopping; ExecStopPost handles forced termination.
        atomic_json(self.state / 'resume.json', containers)
        try:
            self.command([self.docker, 'stop', '--time', '30', *containers], timeout=120)
            for name, source in mounts:
                with tarfile.open(bundle / (name + '.tar.gz'), 'w:gz') as archive:
                    archive.add(source, arcname='.', recursive=True)
        finally:
            self.resume()

    def service_state(self, bundle):
        self.volume_state(bundle, [('proxy', ['/data', '/config']), ('grafana', ['/var/lib/grafana'])])

    def data_store_state(self, bundle):
        manifest = json.loads((bundle / 'store-recovery.json').read_text())
        providers = {row['provider'] for row in manifest['resources'] if row['state'] != 'purged'} - {'postgresql'}
        if 'neo4j' in providers:
            self.neo4j_state(bundle, manifest)
            providers.remove('neo4j')
        volumes = {'s3': ('rustfs', ['/data']), 'qdrant': ('qdrant', ['/qdrant/storage']),
                   'opensearch': ('opensearch', ['/usr/share/opensearch/data'])}
        if providers - volumes.keys():
            raise BackupError('Data-store provider has no protected volume capture')
        if providers:
            self.volume_state(bundle, [volumes[p] for p in sorted(providers)])

    def neo4j_state(self, bundle, manifest):
        """Cleanly stop only catalog-owned dedicated instances; preserve retired volumes."""
        containers, mounts = [], []
        for row in manifest['resources']:
            if row['provider']!='neo4j' or row['state']=='purged': continue
            rid=str(uuid.UUID(row['resource_id']))
            name='platform-neo4j-'+uuid.UUID(rid).hex
            info=json.loads(self.command([self.docker,'inspect',name]))[0]
            if info['Config']['Labels'].get('developer-platform.neo4j-resource')!=rid:
                raise BackupError('Dedicated instance ownership mismatch')
            found=[m for m in info['Mounts'] if m['Destination']=='/data' and m['Type']=='volume' and m['Name']==name+'-data']
            if len(found)!=1: raise BackupError('Dedicated retained volume missing')
            if info['State']['Running']: containers.append(info['Id'])
            mounts.append((name,Path(found[0]['Source'])))
        atomic_json(self.state/'resume.json',containers)
        try:
            if containers:self.command([self.docker,'stop','--time','60',*containers],timeout=180)
            identities=[]
            for name,source in mounts:
                info=json.loads(self.command([self.docker,'inspect',name]))[0]
                if info['State']['Running'] or info['State'].get('ExitCode')==137:
                    raise BackupError('Dedicated instance did not stop cleanly')
                identities.append({'resource_id':info['Config']['Labels']['developer-platform.neo4j-resource'],
                    'image_id':info['Image'],'configured_image':info['Config']['Image']})
                # Stopped physical volume preserves graph data and native system identities.
                with tarfile.open(bundle/(name+'-data.tar.gz'),'w:gz') as archive:
                    archive.add(source,arcname='.',recursive=True)
            atomic_json(bundle/'neo4j-instances.json',identities)
        finally:
            self.resume()

    def postgres_argv(self, *arguments):
        return [self.docker, 'compose', 'exec', '-T', 'postgres', *arguments]

    @contextmanager
    def catalog_snapshot(self):
        """Freeze resource/grant lifecycle across database enumeration and intent capture.

        Non-PostgreSQL resources require a coordinated pause of managed data
        leases across the SQL dump and stopped-service volume capture. The pause
        expires after 35 minutes even if the process is killed. Deadlines continue.
        Closing the psql stdin releases the session lock even after interruption.
        """
        process = subprocess.Popen(self.postgres_argv('psql','-X','-qAt','-v','ON_ERROR_STOP=1',
            '-U','postgres','-d','platform'), cwd=self.root, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        try:
            process.stdin.write(b"""SET lock_timeout='30s'; SET idle_session_timeout='35min'; SELECT pg_advisory_lock(731904);
DO $$ BEGIN
 IF to_regclass('public.store_resources') IS NOT NULL THEN
  UPDATE store_control SET backup_until=now()+interval '35 minutes' WHERE singleton AND EXISTS(
   SELECT 1 FROM store_resources WHERE provider<>'postgresql' AND state<>'purged');
 END IF;
END $$;
DO $$ BEGIN
 IF to_regclass('public.store_control') IS NOT NULL THEN
  IF EXISTS(SELECT 1 FROM store_control WHERE singleton AND backup_until>now()) THEN
   PERFORM pg_sleep(5);
   IF EXISTS(WITH managed AS MATERIALIZED (
    SELECT pid FROM pg_stat_activity WHERE datname ~ '^resource_[a-f0-9]{32}$'
     AND usename ~ '^credential_[a-f0-9]{32}$')
    SELECT 1 FROM managed WHERE NOT pg_terminate_backend(pid,5000)) THEN
     RAISE EXCEPTION 'managed store sessions did not quiesce';
   END IF;
  END IF;
 END IF;
END $$;
\\echo STORE_CATALOG_SNAPSHOT
""")
            process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                for _ in range(10):
                    if not selector.select(timeout=40):
                        raise BackupError('catalog snapshot lock timed out')
                    line = process.stdout.readline()
                    if line.strip() == b'STORE_CATALOG_SNAPSHOT':
                        break
                    if not line:
                        raise BackupError('catalog snapshot lock unavailable')
                else:
                    raise BackupError('catalog snapshot lock handshake failed')
            yield
        finally:
            try:
                process.communicate(b"DO $$ BEGIN IF to_regclass('public.store_control') IS NOT NULL THEN UPDATE store_control SET backup_until=NULL WHERE singleton; END IF; END $$; SELECT pg_advisory_unlock(731904);\n\\q\n", timeout=5)
            except Exception:
                process.kill(); process.wait(timeout=5)
            if process.returncode:
                raise BackupError('catalog snapshot connection failed')

    def dump(self, bundle):
        with (bundle / 'postgres.sql.gz').open('wb') as output:
            with subprocess.Popen(self.postgres_argv('pg_dumpall', '-U', 'postgres'), cwd=self.root,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
                try:
                    with gzip.GzipFile(fileobj=output, mode='wb') as compressed:
                        shutil.copyfileobj(process.stdout, compressed)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
                if process.wait() != 0:
                    raise BackupError('database capture failed')

    def check_graph_sources(self):
        """A retained AGE graph must have a protected source before backup succeeds."""
        arguments = ('exec','-T','postgres','psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres','-d')
        exists = self.compose(*arguments, 'platform', '-c', "SELECT to_regclass('public.store_resources') IS NOT NULL").strip()
        if exists == b'f':
            return
        if exists != b't':
            raise BackupError('store catalog unavailable')
        resources = json.loads(self.compose(*arguments, 'platform', '-c',
            "SELECT COALESCE(jsonb_agg(resource_id),'[]'::jsonb) FROM store_resources WHERE state IN ('active','retired') AND extensions ? 'age'"))
        for identity in resources:
            database = 'resource_' + uuid.UUID(identity).hex
            valid = self.compose(*arguments, database, '-c', """WITH sources AS (
                SELECT DISTINCT ON(graph_name) graph_name,payload->>'state' AS state
                FROM platform_control.graph_sources ORDER BY graph_name,ordinal DESC)
                SELECT NOT EXISTS(SELECT 1 FROM ag_catalog.ag_graph g LEFT JOIN sources s ON s.graph_name=g.name::text
                    WHERE s.graph_name IS NULL OR s.state IS DISTINCT FROM 'active')""").strip()
            if valid != b't':
                raise BackupError('AGE graph has no active protected source')

    def store_recovery_manifest(self, bundle):
        """Purge intent becomes durable off-host BEFORE the data is deleted."""
        arguments = ('exec', '-T', 'postgres', 'psql', '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1',
                     '-U', 'postgres', '-d', 'platform', '-c')
        exists = self.compose(*arguments, "SELECT to_regclass('public.store_resources') IS NOT NULL").strip()
        if exists == b't':
            data = self.compose(*arguments, """SELECT jsonb_build_object('format',1,'captured_at',now(),
                'resources',COALESCE(jsonb_agg(jsonb_build_object('resource_id',resource_id,
                'owner_project',owner_project,'name',name,'quota_bytes',quota_bytes,
                'provider',provider,'state',state,'version',version,
                'extensions',extensions,'configuration',configuration) ORDER BY resource_id),'[]'::jsonb)) FROM store_resources""")
            manifest = json.loads(data)
        elif exists == b'f':
            manifest = {'format': 1, 'resources': []}
        else:
            raise BackupError('store recovery catalog unavailable')
        target = bundle / 'store-recovery.json'
        atomic_json(target, manifest)
        target.chmod(0o600)

    def acknowledge_store_purges(self, bundle, snapshot):
        path = bundle / 'store-recovery.json'
        if not path.exists():
            return  # Legacy bundles and isolated backup-unit fixtures.
        manifest = json.loads(path.read_text())
        pending = [r for r in manifest['resources'] if r['state'] == 'purging']
        if not pending:
            return
        # Only JSON from the immutable, read-back verified bundle is acknowledged.
        # Hex avoids shell/SQL quoting of display names and arbitrary source text.
        payload = json.dumps({'snapshot': snapshot, 'resources': pending}).encode().hex()
        statement = """WITH manifest AS (SELECT convert_from(decode('%s','hex'),'UTF8')::jsonb AS value),
            captured AS (SELECT entry.item,m.value->>'snapshot' AS snapshot FROM manifest m
                CROSS JOIN LATERAL jsonb_array_elements(m.value->'resources') AS entry(item))
            UPDATE store_resources r SET purge_backup_version=r.version,purge_backup_snapshot=c.snapshot
            FROM captured c WHERE r.resource_id=(c.item->>'resource_id')::uuid
                AND r.version=(c.item->>'version')::bigint AND r.state='purging'""" % payload
        self.compose('exec', '-T', 'postgres', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
            '-U', 'postgres', '-d', 'platform', '-c', statement)

    def project_secrets(self, bundle):
        """Write every project's app-secrets into the bundle; restic encrypts the bundle before upload.

        Failing closed: a bundle that silently lacked secrets would look like a valid recovery point.
        """
        kubeconfig = self.root / '.runtime/admin.kubeconfig'
        if not kubeconfig.is_file():
            raise BackupError('cluster credentials missing')
        kubectl = self.config.get('kubectl') or shutil.which('kubectl') or '/usr/local/bin/kubectl'
        listing = json.loads(self.command([kubectl, '--kubeconfig', str(kubeconfig), 'get', 'secrets',
                                           '--all-namespaces', '--field-selector', 'metadata.name=app-secrets',
                                           '-o', 'json'], timeout=60))
        projects = {}
        for item in listing.get('items', []):
            metadata = item.get('metadata', {})
            namespace = metadata.get('namespace', '')
            if not namespace.startswith('project-') or not item.get('data'):
                continue
            projects[namespace[len('project-'):]] = {
                'data': item['data'],
                'annotations': {k: v for k, v in (metadata.get('annotations') or {}).items()
                                if k.startswith('platform.example/changed-')}}
        target = bundle / 'project-secrets.json'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump({'format': 1, 'projects': projects}, output, sort_keys=True)

    def capture(self, bundle):
        self.stage = 'database capture'
        with self.catalog_snapshot():
            self.check_graph_sources()
            self.stage = 'store recovery intent capture'
            self.store_recovery_manifest(bundle)
            self.stage = 'coordinated data-store volume capture'
            self.data_store_state(bundle)
            # A clean service stop resolves any in-flight non-SQL writes before
            # the SQL snapshot. Managed leases remain paused after restart.
            self.stage = 'database capture'
            self.dump(bundle)
        self.stage = 'project secret capture'
        self.project_secrets(bundle)
        self.stage = 'configuration capture'
        with tarfile.open(bundle / 'platform-files.tar.gz', 'w:gz') as archive:
            for name in ['compose.yaml', '.env', 'scripts', 'platform', 'infrastructure', 'persistence', 'identity']:
                source = self.root / name
                if not source.exists():
                    raise BackupError('required source missing')
                archive.add(source, arcname=name,
                            filter=lambda item: None if '__pycache__' in Path(item.name).parts else item)
            # Older deployed checkouts retain the manual helper in scripts/.
            backup_scripts = self.root / 'operations/backup/scripts'
            if backup_scripts.exists():
                archive.add(backup_scripts, arcname='operations/backup/scripts',
                            filter=lambda item: None if '__pycache__' in Path(item.name).parts else item)
            store_configuration = self.root / '.runtime/stores'
            if store_configuration.exists():
                archive.add(store_configuration, arcname='.runtime/stores')
        config_dir = Path(self.config.get('config_dir', '/etc/developer-platform'))
        with tarfile.open(bundle / 'host-config.tar.gz', 'w:gz') as archive:
            archive.add(config_dir, arcname='etc/developer-platform')
            for name in ['platform-heartbeat.service', 'platform-heartbeat.timer',
                         'platform-backup.service', 'platform-backup.timer',
                         'platform-backup-recover.service', 'platform-backup-notify.service',
                         'platform-backup-notify.timer']:
                unit = Path('/etc/systemd/system') / name
                if unit.exists():
                    archive.add(unit, arcname='etc/systemd/system/' + name)
        for name in ['platform-backup', 'platform-restic']:
            shutil.copy2(Path('/usr/local/sbin') / name, bundle / name)
        self.stage = 'service state capture'
        self.service_state(bundle)
        image_records = []
        for container in self.compose('ps', '-q').decode().split():
            info = json.loads(self.command([self.docker, 'inspect', container]))[0]
            image = json.loads(self.command([self.docker, 'image', 'inspect', info['Image']]))[0]
            image_records.append({'name': info['Name'], 'reference': info['Config']['Image'],
                                  'id': info['Image'], 'digests': image.get('RepoDigests', [])})
        metadata = {
            'images': image_records,
            'containers': self.compose('ps', '--format', 'json').decode(),
            'postgres_version': self.compose('exec', '-T', 'postgres', 'postgres', '--version').decode().strip(),
            'restic_version': self.command([self.restic, 'version']).decode().strip(),
            'source_revision': self.config.get('source_revision', 'unknown; source files included'),
        }
        # docker compose ps exposes names/images/status, not container environments.
        atomic_json(bundle / 'versions.json', metadata)

    def verify(self, snapshot, bundle, work):
        target = work / 'readback'
        self.command([self.restic, 'restore', snapshot, '--target', str(target)])
        manifests = list(target.rglob('manifest.json'))
        if len(manifests) != 1 or manifests[0].read_bytes() != (bundle / 'manifest.json').read_bytes():
            raise BackupError('manifest readback mismatch')
        manifest = json.loads(manifests[0].read_text())
        for name, checksum in manifest['sha256'].items():
            if digest(manifests[0].parent / name) != checksum:
                raise BackupError('snapshot readback mismatch')

    def retention(self):
        # Only verified platform snapshots for this installation are eligible.
        self.command([self.restic, 'forget', '--host', self.config['instance'],
                      '--tag', 'developer-platform,verified', '--group-by', 'host',
                      '--keep-last', '1', '--keep-daily', '14', '--keep-weekly', '8',
                      '--keep-monthly', '6', '--prune'])
        self.command([self.restic, 'check'])

    def run(self):
        self.resume()
        work = self.state / 'work'
        if work.exists():
            shutil.rmtree(work)
        bundle = work / 'bundle'
        bundle.mkdir(mode=0o700, parents=True)
        started = int(time.time())
        run_id = uuid.uuid4().hex
        event = {'run_id': run_id, 'started': started, 'event': 'start'}
        previous = self.read('status.json', {})
        status = {'run_id': run_id, 'started': started, 'running': True,
                  'last_verified_capture': previous.get('last_verified_capture'),
                  'last_verified_snapshot': previous.get('last_verified_snapshot')}
        atomic_json(self.state / 'status.json', status)
        self.queue(event)
        try:
            self.capture(bundle)
            manifest = {'format': 1, 'run_id': run_id, 'captured_at': started,
                        'instance': self.config['instance'],
                        'sha256': {p.name: digest(p) for p in sorted(bundle.iterdir())}}
            atomic_json(bundle / 'manifest.json', manifest)
            self.stage = 'encrypted upload'
            output = self.command([self.restic, 'backup', '--json', '--host', self.config['instance'],
                                   '--tag', 'developer-platform', '--tag', 'pending',
                                   '--tag', 'run-' + run_id, 'bundle'], cwd=work)
            summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
            ids = [item['snapshot_id'] for item in summaries if item.get('message_type') == 'summary']
            if len(ids) != 1 or not re.fullmatch('[0-9a-f]{8,64}', ids[0]):
                raise BackupError('snapshot ID missing')
            self.stage = 'snapshot readback'
            self.verify(ids[0], bundle, work)
            self.command([self.restic, 'tag', '--remove', 'pending', '--add', 'verified', ids[0]])
            snapshots = json.loads(self.command([self.restic, 'snapshots', '--json', '--host', self.config['instance'],
                '--tag', 'developer-platform,verified,run-' + run_id]))
            if len(snapshots) != 1:
                raise BackupError('verified snapshot identity ambiguous')
            snapshot = snapshots[0]['id']
            status.update(last_verified_capture=started, last_verified_snapshot=snapshot)
            atomic_json(self.state / 'status.json', status)
            self.stage = 'verified store purge acknowledgment'
            self.acknowledge_store_purges(bundle, snapshot)
            self.stage = 'retention'
            self.retention()
            status.update(running=False, result='success', stage='complete', finished=int(time.time()))
            atomic_json(self.state / 'status.json', status)
            delivered = self.queue(dict(event, event='success', snapshot=snapshot))
            print('Backup verified and retention completed; snapshot=' + snapshot)
            return 0 if delivered else 1
        except Exception:
            # Preserve the last verified snapshot, even if subsequent retention failed.
            status.update(running=False, result='failure', stage=self.stage, finished=int(time.time()))
            atomic_json(self.state / 'status.json', status)
            self.queue(dict(event, event='failure'))
            print('Backup failed during ' + self.stage + '; see status.json for the last verified recovery point.', file=sys.stderr)
            return 1
        finally:
            self.resume()
            if work.exists():
                shutil.rmtree(work)

    def recover(self):
        self.resume()
        status = self.read('status.json', {})
        if status.get('running'):
            status.update(running=False, result='failure', stage='interrupted', finished=int(time.time()))
            atomic_json(self.state / 'status.json', status)
            self.queue({'run_id': status['run_id'], 'started': status['started'], 'event': 'failure'})
        work = self.state / 'work'
        if work.exists():
            shutil.rmtree(work)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['run', 'recover', 'notify'])
    parser.add_argument('--config', default='/etc/developer-platform/backup/job.json')
    args = parser.parse_args()
    os.umask(0o077)
    job = Job(json.loads(Path(args.config).read_text()))
    with (job.state / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # A running backup owns the outbox and recovery intent as well.
            return 0 if args.action == 'notify' else 1
        def interrupted(*_):
            raise BackupError('interrupted')
        signal.signal(signal.SIGTERM, interrupted)
        try:
            if args.action == 'run':
                return job.run()
            if args.action == 'recover':
                job.recover()
                return 0
            return 0 if job.retry_notification() else 1
        except Exception:
            print('Backup maintenance failed; inspect service state and status.json.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(main())
