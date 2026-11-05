# Intentional isolated fault/evaluation demonstration

PREPARED ONLY; none of these service/fault commands were executed in submission
preparation. The main authenticated demo has NO published simulator port 8102.
Its protected ticket list is app `/demo/tickets`, after `/demo/login`.

Use only a separately authorized rehearsal with approved API budget in a
SEPARATE clone, with its own `.env`, generated credentials and data. A project
name alone does not isolate relative bind mounts. Never use the owner's retained
clone/data or existing pending draft. No simulator reset is required on main.

For an isolated fixture, copy `docker-compose.yml` to a private local file named
`docker-compose.isolated.local.yml` in that separate clone, and replace (not
append) the mappings: app `127.0.0.1:8001:8000`, UI `127.0.0.1:7861:7860`, simulator
`127.0.0.1:8104:8102`. Set UI `APP_PUBLIC_URL` to `http://127.0.0.1:8001`; retain
internal service URLs. Keep the separate clone's data and read-only demo-sheet
mounts. Check that ports are unused and do not display effective secret values.
Generate logins as in the README before starting that isolated config.

```powershell
# Future-only: separate prepared clone/config, not the retained main installation.
docker-compose -p nakhla-helpdesk-fault-demo -f docker-compose.isolated.local.yml up --build -d --wait
```

Then the intentional simulator-only reset/fault demonstration below is allowed
ONLY when separately authorized. It operates on host 8104, not default/main 8102.
Reset destroys that isolated simulator's created tickets/logs; export any needed
evidence privately first. It never resets app history or any spending ledger.
See [paste-ready fault commands](demo-commands.txt). Reusing a draft requires the
actual approval control and explicit authorization; strings never substitute.

For original eval/check-kit paths expecting 8102, the shipped optional
`docker-compose.eval.yml` override is retained: use it only in an isolated copy
where 8102 is unused, with its own data/credentials and budget. The main published
demo remains internal-only. Stop only the isolated project afterward; retain data
and unknown spending reservations. No `down -v` or database restore.
