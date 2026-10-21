# Repository guidelines

These guidelines apply throughout the repository.

## Readability and comments

- Write code and scripts for a human reader. Use descriptive names, consistent
  indentation, and whitespace to separate logical steps.
- Split longer scripts into clearly labeled sections. Expand dense one-line
  conditionals, loops, and case branches when doing so makes control flow easier
  to follow.
- Add comments that explain intent, prerequisites, ordering constraints, and
  non-obvious behavior. Explain credential permissions and operational side
  effects where readers need that context.
- Keep comments accurate when changing code. Avoid comments that merely repeat
  the adjacent command or implementation.
- Keep readability-only changes behavior-preserving unless a functional change
  is explicitly part of the task.

## Directory and module structure

- Organize files by component, purpose, and responsibility. Follow the existing
  repository layout and naming conventions when adding code.
- Keep each module focused on a coherent responsibility. Split modules or flat
  directories when distinct responsibilities become difficult to navigate; avoid
  unnecessary nesting and tiny modules that only add indirection.
- Keep entry points small and easy to find. Place reusable logic in appropriately
  named modules close to the code that uses it, with clear dependency boundaries.
  Avoid generic utility modules that accumulate unrelated behavior.
- Separate setup, generation, validation, operational commands, and shared
  test support where they have different purposes. Follow `scripts/README.md`
  and `ansible/README.md` when adding repository automation.
- Under `scripts/` and `ansible/`, group tests by execution environment:
  offline `unit/`, focused integration `components/` where applicable, and
  running-platform `platform/`. Keep reusable fixtures in test `support/`;
  avoid parallel acceptance, verification, and drill directory taxonomies.
- When moving files or changing module boundaries, update imports, callers,
  workflows, tests, documentation, and paths derived from file locations. Verify
  the supported invocation methods after the change.
- Reusable platform test runners live in `tests/platform/`, their offline tests
  in `tests/platform/unit/`, and deployable test applications in `tests/fixtures/`.
  Keep operator entry points under `scripts/tests/platform/` and application
  unit tests beside the application.
- Keep structural refactoring scoped to the task and preserve behavior unless a
  functional change is requested.

## Linting and validation

- Run the relevant linters and format checks for files you change before
  considering the work complete. Python-installable quality tools are listed in
  the root `requirements.txt`.
- Use the following checks as applicable, targeting the changed files or their
  containing component:
  - Python: `ruff check <paths>` and `ruff format --check <paths>`.
  - YAML: `yamllint <paths>`.
  - Ansible playbooks and roles: `ansible-lint <paths>` and the applicable
    `ansible-playbook --syntax-check` with the component's inventory.
  - Shell scripts: `shellcheck <paths>` and the appropriate shell syntax check
    (`bash -n <script>` for Bash).
  - Markdown: `pymarkdown scan <files>` (or `pymarkdown scan --recurse <directory>`)
    and `mdformat --check <paths>`. Use `mdformat <paths>` to apply formatting;
    install `mdformat-gfm` to preserve GitHub tables and task lists.
  - Dockerfiles: `hadolint <paths>`; install `hadolint-py` from the root
    `requirements.txt` to provide the `hadolint` command.
  - Docker Compose: `docker compose config --quiet` with the relevant files,
    profiles, and environment configuration.
  - UI (`platform/ui/`): `npm run lint`, `npm run format:check`, and
    `npm run typecheck`. Run `npm run check` for the API contract check, lint,
    formatting, type checking, unit tests, and production build. Browser tests
    run separately with `npm run test:e2e`.
  - Other languages and components: use their existing lint and format commands.
- Fix issues introduced by your changes. Keep unrelated cleanup separate; report
  existing failures, missing tools, or checks that could not run and explain why.
  Do not suppress checks solely to obtain a passing result.
- Run tests appropriate to the change in addition to linting. For script changes,
  verify affected callers, imports, and paths. Validate operational scripts
  without starting a deployment or live drill unless the task authorizes it.

## UI code quality

- Install UI development tools with npm in `platform/ui/` and commit changes to
  `package.json` and `package-lock.json` together. Use `npm ci` for reproducible
  installs; these tools do not belong in the Python requirements.
- Use the existing type-aware ESLint rules, React Hooks rules, and recommended
  JSX accessibility rules (`eslint-plugin-jsx-a11y-x` for ESLint 10). Treat lint
  warnings as failures. Give controls accessible names, associate labels with
  inputs, and use semantic elements.
  Static accessibility checks complement browser and keyboard testing.
- Use Prettier for UI source and configuration formatting, with the committed
  settings. Run `npm run format` to apply formatting. Keep formatting rules out
  of ESLint; apply `eslint-config-prettier` after the other ESLint presets.
- Use the Tailwind Prettier plugin with `src/index.css` as the stylesheet entry
  point. Sort classes in JSX and in `cn()` and `cva()` calls automatically.
- Exclude generated API types and build/test output from lint and formatting;
  regenerate API types with `npm run api:generate` and verify with
  `npm run api:check`. Markdown continues to use the repository's Markdown
  tools, and YAML continues to use its existing checks.
- Group UI code by feature under `src/features/`, reusable visual primitives
  under `src/components/ui/`, and application composition under `src/app/`.
  Keep API adapters, authentication, and shared test setup in their respective
  modules. Co-locate component and feature unit tests; keep browser scenarios
  under `e2e/`. Split complex components along clear responsibilities and add
  comments for intent or non-obvious behavior.
