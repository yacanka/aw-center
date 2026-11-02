# Managed runtime trust boundary

The extracted source package is reviewed executable input. A package mirror,
offline bundle manifest, cache receipt, or previously installed runtime is not a
source of executable authorization. The source catalog pins original archives.
No runtime is installed globally and no machine PATH is changed.

Before CMD starts any cached or newly extracted interpreter:

1. It rejects unexpected entries beside Python and in its parent runtime
   directory. This excludes `python311.zip`, `python._pth`/`python311._pth`,
   `.local` redirection and `pyvenv.cfg` startup controls.
2. Native certutil verifies the shipped `installation_python_startup.sha256`:
   every top-level native/control file (including every DLL), plus both `.py`
   and shipped `.pyc` forms of `encodings.__init__`, `aliases` and `utf_8`.
   Extension modules in the encoding directory and same-name `aliases`/`utf_8`
   packages are rejected because they could shadow the reviewed source modules.
3. Python starts with `-I -S -B -X utf8 -X frozen_modules=on`: environment/user
   paths and site processing are disabled; UTF-8 and the frozen bootstrap,
   codecs and path machinery come from the verified Python DLL.
4. `installation_verify_python.py` first checks that `nt` and `_sha256` are
   builtins, then imports only those builtins and `sys`. It reads the complete
   reviewed inventory as bytes, decodes through the pinned UTF-8 codec and
   authenticates all 3,983 archive files. Links, reparse points, missing files,
   unexpected files and unexpected directories fail closed. Only the exact
   inert root `.awcenter-tool.json` receipt is exempt; its contents are never
   parsed as expected hashes.
5. Only after complete verification does it add the source root to `sys.path`
   and import owner-permission or launcher code. Doctor uses the same chain
   without downloads, extraction or writes.

Managed child environments disable bytecode writes and Python user hooks and
clear Node startup hooks. This keeps the baseline runtime immutable and prevents
inherited `NODE_OPTIONS` from executing code during version checks. Node and npm
inspection derives expected hashes by reading the cache archive **after** its
catalog SHA-256 passes; mutable receipt hashes cannot authorize changed code.
Inspection does not extract archives, execute runtimes or write files.

Both curl branches use `--disable` as their first option, preventing per-user
`_curlrc`/`.curlrc` from enabling insecure TLS or injecting transfers. Public,
repository and offline bytes must all match the same source pin. Python HTTPS
retrieval adds an explicit CA bundle to the system roots and never disables TLS
verification. Native curl accepts an explicit CA bundle using `--cacert`.

## Reproducing the Python inventories

Obtain the exact official archive named by `installation_catalog.json`, then run:

```text
python scripts/launcher/generate_python_inventory.py PATH_TO_PINNED_ARCHIVE
```

The generator verifies the archive's existing catalog SHA-256 before reading
members and emits deterministic LF manifests. Review catalog, both inventories,
CMD root allowlist and the documented startup closure together when upgrading
Python. Inventory generation is a maintainer action, never an install-time trust
step. The generator does not execute or install the downloaded interpreter.

The Windows-only smoke suite exercises native CMD, exact ACLs, a hostile curl
configuration and modified DLL/encoding/source/startup-control files. Portable
unit tests validate the complete inventory and injected files independently.
Actual Windows startup and corporate TLS still require the native acceptance run.
