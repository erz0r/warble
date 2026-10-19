en_vccv with an outdated `envccv.yaml` (version 1.0, older than the 1.3 template). openutau migrates such a file
in place when it loads the bank (and writes `envccv_backup(1.0).yaml`); warble does the same merge in memory.

`gen_goldens.py en_vccv_migrated_yaml` therefore rewrites this bank's `envccv.yaml`. restore the original
version-1.0 file afterwards (and delete the backup) so the parity test keeps exercising the in-memory migration;
the golden is the same either way.
