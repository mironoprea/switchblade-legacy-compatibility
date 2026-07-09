# Backup validation and restore safety specification

## Archive contract

- ZIP archive with exactly one `manifest.json`.
- Manifest format is integer `1` and `files` is a list.
- Each file record contains `path`, non-negative integer `size`, and SHA-256.
- Restorable members begin with `data/` and map through fixed logical roots.
- Reject duplicate names, undeclared data members, unsupported extra members,
  absolute/drive-qualified/backslash paths, empty components, `.` and `..`.
- Verify every declared member's existence, size, and digest before mutation.

## Allowed logical roots

- `Synapse/Devices/DeathStalker Ultimate/Profiles`
- `Synapse/Accounts/User/Devices/DeathStalker Ultimate/Profiles`
- `Synapse/Accounts/User/Macros`
- `SwitchBlade/DeathStalker`
- `SwitchBlade/Apps/Razer`

The archive never supplies a physical destination. Account-scoped data may be
restored only when exactly one local account directory exists.

## Content allowlist

Allow `config.xml`, `profiles.json`, and suffixes `.xml`, `.png`, `.jpg`, `.jpeg`,
`.bmp`, `.rzdisplaystate`. Exclude analytics, logs, `RazerLoginData.xml`, binaries,
drivers, and arbitrary extensions during both backup and restore.

## Restore sequence

1. Require explicit confirmation.
2. Refuse while exact legacy processes are running.
3. Validate the entire archive.
4. Resolve fixed destinations.
5. Create a pre-restore backup with driver export disabled.
6. Stage content below the utility data directory.
7. Replace only declared files, using same-directory temporary files and
   `os.replace` where practical.
8. Never delete unrelated destination files.
9. Append privacy-safe JSONL events for start, backup, each file, completion, or
   failure.

## Journal privacy

Record UTC timestamp, operation ID, event, archive basename, and neutral logical
paths. Never record file contents, usernames, real account directory names,
environment variables, credentials, or sensitive exception paths.

## Open hardening requirements

The existing code meets the base contract above. Before consumer release, add
resource limits, Windows case-collision checks, reparse-point protection,
collision-resistant artifacts, and operation-level failure recovery as described
in `BUILD_PLAN.md`.
