# Downloaded upstream sources

Use this directory for pinned upstream RTL repositories, their existing
testbenches, and external verification dependencies. Preserve upstream directory
layouts and record exact revisions, dependency identities, and license references
in the corresponding target configuration.

Git ignores the contents of this directory except this README. Commit
reproduction instructions and reviewed patches rather than downloaded repository
trees. Keep upstream sources unchanged and apply controlled mutations in isolated
run workspaces.

Pass repository-relative input paths such as `vendor/<repository>/rtl` to the
launcher under `tooling/`, regardless of the host's current directory. The
launcher mounts the repository root; this directory does not automatically fetch
or prepare dependencies.
