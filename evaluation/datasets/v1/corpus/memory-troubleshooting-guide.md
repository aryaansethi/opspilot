# Memory Troubleshooting Guide

## JVM heap exhaustion

`java.lang.OutOfMemoryError: Java heap space` means the JVM heap (set by `-Xmx`) is full. Capture a heap dump with `-XX:+HeapDumpOnOutOfMemoryError` and look for unbounded caches or large collections.

## Container killed by the kernel

Exit code 137 with reason `OOMKilled` means the container exceeded its memory limit and the kernel killed it. This is different from a JVM heap error: the process can be killed even if the heap is not full, for example because of native memory or a heap set too close to the container limit.
Keep `-Xmx` at or below 75 percent of the container memory limit.

## Long garbage collection pauses

GC pauses above 1 second cause request timeouts. Check the GC log; frequent full GCs usually mean the heap is too small for the live data set.

## Node.js services

Node.js services default to a heap limit far below large container sizes. Set `--max-old-space-size` explicitly.
