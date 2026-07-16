# ADR-0001: Isolate long-running Houdini jobs

## Status

Accepted

## Context

Houdini scene APIs require host-thread coordination, while renders can run for
hours. Keeping render execution on that thread blocks the UI. `hwebserver`
provides HTTP ingress, but its Python handlers do not provide the host-thread
execution guarantee needed by `hou.*` and therefore cannot replace the adapter's
event-loop bridge.

Cancellation must also avoid PID reuse hazards. A PID copied from a status file
does not prove that a process is still the child originally launched by this
adapter instance.

## Decision

- Keep the existing Houdini event-loop bridge for short scene validation and job launch.
- Run long render work in an isolated `hython` process group.
- Retain each launched `Popen` handle in the adapter process and cancel only through that owned handle.
- Persist job status for observation, but never treat a persisted PID as process ownership evidence.
- Treat `hwebserver` as optional ingress only; it does not execute `hou.*` directly for long jobs.

## Consequences

### Positive

- Houdini remains responsive during long renders.
- Cancellation can terminate the owned worker tree without risking an unrelated process.
- Polling and cancellation need no Houdini main-thread affinity.

### Negative

- Jobs started by an adapter instance cannot be cancelled after that instance restarts.
- Process-tree termination remains platform-specific (`taskkill /T` on Windows, process groups on POSIX).

## Alternatives Considered

- Run render calls on the host thread: rejected because it blocks interactive Houdini.
- Replace the bridge with `hwebserver`: rejected because HTTP handler threads are not a `hou.*` thread-safety contract.
- Cancel by status-file PID: rejected because persisted PIDs do not prove ownership and may be reused.
- Use `hrpyc` or `openport` as the control plane: rejected because they do not provide this typed job lifecycle and ownership contract.

## References

- https://www.sidefx.com/docs/houdini/hwebserver/index.html
- https://www.sidefx.com/docs/houdini/hwebserver/apiFunction.html
- https://www.sidefx.com/docs/houdini/hom/hou/ui.html
- https://www.sidefx.com/docs/houdini/hom/rpc
