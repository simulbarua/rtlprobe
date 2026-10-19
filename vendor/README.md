# Downloaded upstream sources

Use this directory for pinned upstream RTL repositories, their existing
testbenches, and external verification dependencies. Preserve upstream directory
layouts and record exact revisions, dependency identities, and license references
in the corresponding target configuration.

Git ignores the contents of this directory except this README. Commit
reproduction instructions and reviewed patches rather than downloaded repository
trees. Keep upstream sources unchanged and apply controlled mutations in isolated
run workspaces.

The existing scripts under `tooling/` retain their documented input paths. This
new directory does not automatically change or fetch their dependencies.
