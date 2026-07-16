# ADR-0001: Isolate long-running Houdini jobs

## Status

Accepted

## Context

Houdini scene APIs require host-thread coordination, while renders can run for
hours. Keeping render execution on that thread blocks the UI. `hwebserver`
provides HTTP ingress, but its Python handlers do not provide the host-thread
execution guarantee needed by `hou.*` and therefore cannot replace the adapter's
event-loop bridge.

Houdini also exposes remote and Engine-oriented APIs, but they solve different
problems. `hrpyc` proxies HOM into a live interpreter without authentication and
is therefore suitable only for trusted local debugging. HAPI/HARS provides an
isolated Houdini Engine session and is a useful future backend for HDA-centric
cooks, but it is not a transparent replacement for the state of an already-open
Houdini GUI session. SessionSync narrows that gap for client-created assets while
retaining explicit synchronization limits.

Cancellation must also avoid PID reuse hazards. A PID copied from a status file
does not prove that a process is still the child originally launched by this
adapter instance.

## Decision

- Keep the existing Houdini event-loop bridge for short scene validation and job launch.
- Run long ROP render, simulation-cache, and output-chain work through the same
  isolated `hython` worker process group.
- Retain each launched `Popen` handle in the adapter process and cancel only through that owned handle.
- Persist job status for observation, but never treat a persisted PID as process ownership evidence.
- Reject interactive isolated launch when the HIP is unsaved or has unsaved
  changes; never auto-save the user's GUI scene. For explicit headless isolated
  launch, require an existing HIP and save its current state before spawning the
  worker because Houdini 21 may retain a dirty flag after a successful headless
  save. Reject the launch when that save fails.
- Derive output completion and ETA while polling from expected file signatures;
  do not send a callback to the interactive process for every frame.
- Return bounded poll summaries by default. Full expected-output snapshots,
  written-file lists, errors, and tracebacks require `include_details=true`.
- Treat `hwebserver` as optional ingress only; it does not execute `hou.*` directly for long jobs.
- Keep `hrpyc` out of the default control plane; allow it only as an explicitly
  enabled trusted-local debugging transport.
- Allow a future HAPI/HARS backend for isolated HDA/Engine workloads, behind the
  same typed job/status/cancel contract rather than pretending it controls the
  complete live GUI scene.

## Consequences

### Positive

- Houdini remains responsive during long ROP renders, cache bakes, and ROP chains.
- Cancellation can terminate the owned worker tree without risking an unrelated process.
- Polling and cancellation need no Houdini main-thread affinity.

### Negative

- Jobs started by an adapter instance cannot be cancelled after that instance restarts.
- Process-tree termination remains platform-specific (`taskkill /T` on Windows, process groups on POSIX).
- Explicit headless isolated launch saves the current HIP before spawning its
  worker; normal headless execution remains foreground and does not add a save.
- Poll progress is output-file progress, so jobs without a discoverable output
  pattern report unknown progress/ETA.
- ROP chains use execution/cook errors as their completion contract. They may
  complete without a discoverable output pattern and report output verification
  as `unavailable`; render and cache jobs continue to require updated output.

## Alternatives Considered

- Run render calls on the host thread: rejected because it blocks interactive Houdini.
- Replace the bridge with `hwebserver`: rejected because HTTP handler threads are not a `hou.*` thread-safety contract.
- Cancel by status-file PID: rejected because persisted PIDs do not prove ownership and may be reused.
- Use `hrpyc` or `openport` as the control plane: rejected because they do not provide this typed job lifecycle and ownership contract.
- Replace live-session control with HAPI/HARS: rejected as the default because
  Engine sessions and SessionSync do not expose the complete state and behavior
  of an arbitrary already-open Houdini GUI scene. Retained as an optional
  isolated-compute backend.

## References

- https://www.sidefx.com/docs/houdini/hwebserver/index.html
- https://www.sidefx.com/docs/houdini/hwebserver/apiFunction.html
- https://www.sidefx.com/docs/houdini/hom/hou/ui.html
- https://www.sidefx.com/docs/houdini/hom/rpc
- https://www.sidefx.com/docs/hengine/_h_a_p_i__sessions.html
- https://www.sidefx.com/docs/houdini/ref/henginesessionsync.html
