# Physical source line counts

The scanner counts newline-delimited physical lines in eligible indexed source files. A nonempty final line without a newline counts as one line. Empty files count as zero. This is a text line count, not a statement or logical code count.

The count uses the scanner's existing source allowlist and `maxFileBytes` cap. It skips binary files containing a NUL byte, and never writes file contents to the catalog. The total read budget is `maxLineCountBytes`; the default and ceiling are 16 MiB per scan. An owner-private policy may set a lower positive value. This budget is separate from syntax checking and does not change which files are indexed.

The catalog stores counted lines, counted files, pending files, binary files, and a completion flag for each project and overall. A `+` after the dashboard total means it is a lower bound because coverage or line counting is incomplete. A pending file may be unreadable or beyond the byte budget. Binary files do not add lines. A complete line count only covers eligible files within the configured scan policy; excluded or oversized files are outside it.

The checked-in example policy and setup revision 2 bundle remain pinned to their released hashes. Their scanner uses its default line budget unless the owner adds `maxLineCountBytes` to a private policy.
