# Production Docker inventory (read-only)

First step in upgrading the National Library of Latvia NoSketch Engine at https://korpuss.lnb.lv. **No deployment, rebuilding, stopping, restarting, or corpus recompilation is performed.**

## Running on nosketchtest

From the current directory `/home/valdiss/github`:

~~~bash
cd /home/valdiss/github
git clone https://github.com/ValRCS/HowTo_NoSketch.git
cd HowTo_NoSketch
bash upgrade/run_inventory.sh
~~~

The default container is `noske` and the default Docker command is `sudo docker`; sudo may ask for your password. The directory `/home/valdiss/github` is **not itself a Git repository**, so `git status` there naturally fails. After cloning, the new Git repository is `/home/valdiss/github/HowTo_NoSketch`. The existing `NoSketch-Engine-Docker` checkout remains untouched.

## Information collected

- Exact running container image ID/reference, creation time, status, restart policy, AutoRemove, and Docker image metadata/digest.
- **All resolved Docker mounts** including source, destination, type, RW flag; original `HostConfig.Binds` and `HostConfig.Mounts` specifications.
- Published ports, network mode, configured user, Compose-origin labels.
- Environment variable **names**, not sensitive values; a small allowlist of simple non-sensitive values only.
- Host path mapped to `/corpora`, registry layout and immediate corpus subdirectories, and filesystem space. No recursive scan of potentially huge corpora.
- In-container Debian release, NoSketch-related package versions, locales and only the number of immediate entries in Bonito state directories.
- nginx running status and loopback `proxy_pass` references from readable site configuration, but **not** the complete nginx configuration.

## Output and security

Creates a new, private directory outside the Git checkout:

~~~text
/home/valdiss/noske-inventory-YYYYMMDDTHHMMSSZ/
  inventory.md
  inventory.json
~~~

Output directory is mode `0700` and files mode `0600`. Only these local files are created; the process issues no Docker writes, no nginx reload and no corpus commands. It **does not capture raw docker inspect**, certificate material, full nginx config or secret environment values.

Even redacted reports contain private host paths, corpus names and infrastructure topology. **Do not commit generated reports to this public repo.** Review/redact them before sharing.

## Options

~~~bash
bash upgrade/run_inventory.sh --container other-name
bash upgrade/run_inventory.sh --docker-command docker
bash upgrade/run_inventory.sh --skip-container-exec
bash upgrade/run_inventory.sh --output-dir /home/valdiss/noske-inventory-custom
bash upgrade/run_inventory.sh --help
~~~

The `--output-dir` must not already exist and should be outside this checkout. `--skip-container-exec` avoids running even read-only commands inside the container.

If your account cannot list the corpus mount path, the report records the permissions limitation; Docker can still report its mount source. The script will not try to change those permissions.

## Tests

~~~bash
python3 -m unittest discover -s upgrade/tests -v
~~~

## Decision gates

Before any upgrade: verify the original `/corpora` bind mount, additional binds, whether `/var/lib/bonito` is persistent, AutoRemove, exact image ID, and current nginx upstream port. **This script does not create backups and does not establish index compatibility.**
