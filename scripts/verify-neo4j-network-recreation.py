#!/usr/bin/env python3
"""Disposable network-only test of Compose infrastructure replacement."""
import os
import subprocess
from uuid import uuid4
from app.stores.neo4j_controller import Controller,names,LABEL
from app.stores.neo4j import IMAGE


def main():
    prefix='fixture-neo4j-network-'+uuid4().hex[:6]+'-'
    api=prefix+'api'
    platform=prefix+'platform'
    os.environ.update(NEO4J_INSTANCE_PREFIX=prefix,NEO4J_NETWORK_MEMBERS=api)
    rid=uuid4();name,_,network=names(rid)
    def docker(*args):
        value=subprocess.run(['docker',*args],capture_output=True,timeout=30)
        if value.returncode:raise RuntimeError('Disposable network fixture failed')
        return value.stdout.decode().strip()
    def peer():docker('run','-d','--name',api,'--network',platform,'--memory','32m','--entrypoint','sleep',IMAGE,'3600')
    try:
        docker('network','create','--internal',platform)
        docker('network','create','--internal','--label',LABEL+'='+str(rid),network)
        docker('run','-d','--name',name,'--network',network,'--label',LABEL+'='+str(rid),
            '--memory','32m','--entrypoint','sleep',IMAGE,'3600')
        peer();control=Controller()
        control.reconcile_networks()
        first=control.engine.call('GET','/containers/'+api+'/json')
        assert network in first['NetworkSettings']['Networks']
        docker('rm','-f',api);peer()
        before=control.engine.call('GET','/containers/'+api+'/json')
        assert before['Id']!=first['Id'] and network not in before['NetworkSettings']['Networks']
        control.reconcile_networks()
        assert network in control.engine.call('GET','/containers/'+api+'/json')['NetworkSettings']['Networks']
        docker('stop',name);docker('rm','-f',api);peer()
        control.reconcile_networks()
        assert not control.info(rid)['State']['Running']
        assert network not in control.engine.call('GET','/containers/'+api+'/json')['NetworkSettings']['Networks']
        print('PASS recreated Compose peer rejoins owned running-instance network; stopped instances remain stopped and detached')
    finally:
        for target in (api,name):subprocess.run(['docker','rm','-f',target],capture_output=True,timeout=30)
        for target in (network,platform):subprocess.run(['docker','network','rm',target],capture_output=True,timeout=30)

if __name__=='__main__':main()
