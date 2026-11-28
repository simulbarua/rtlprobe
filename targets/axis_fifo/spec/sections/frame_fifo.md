# Fixed 16-bit frame FIFO contract

The source and sink transfer a beat on a rising clock edge with valid and ready
asserted. Frame mode commits a frame at its final beat. Until commit, reads
can only observe previously committed frames. Once a committed beat is
available, the sink can stall it with ready low. The next accepted beat
follows in order, preserving the enabled byte mask, frame boundary, ID,
destination, and user fields.

The selected profile discards frames marked bad on their final beat and
frames that exceed the eight-beat storage capacity. The discard restores the
write position to the last committed boundary so a following valid frame
can still be received. Good, bad, and overflow flags are status pulses.

Frame pause allows a frame in progress to finish before acknowledging the
request. Acknowledged pause suppresses downstream valid until the request
clears. Synchronous reset clears pending and committed contents and releases
pause. Continued writes and reads must preserve ordering across pointer wrap.
