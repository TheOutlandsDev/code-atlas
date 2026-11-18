# Physical source line counts

The scanner counts newline-delimited physical lines in eligible indexed source files. A nonempty final line without a newline counts as one line. Empty files count as zero. This is a text line count, not a statement or logical code count.

The count uses the scanner's existing source allowlist and `maxFileBytes` cap. It skips binary files containing a NUL byte, and never writes file contents to the catalog. The total read budget is `maxLineCountBytes`; the default and ceiling are 16 MiB per scan. An owner-private policy may set a lower positive value. This budget is separate from syntax checking and does not change which files are indexed.

The catalog stores counted lines, counted files, pending files, binary files, and a completion flag for each project and overall. A `+` after the dashboard total means it is a lower bound because coverage or line counting is incomplete. A pending file may be unreadable or beyond the byte budget. Binary files do not add lines. A complete line count only covers eligible files within the configured scan policy; excluded or oversized files are outside it.

## Source changes and fresh scans

The portable scanner creates a new catalog from a fresh bounded walk on each refresh. It has no persistent file-validation cache or resumable discovery queue. A subsequent scan recounts a replaced file from its current source; it does not merge that file's previous line total into the new catalog.

Source reads are bound to the device, inode, size and timestamps observed during discovery. The scanner checks the open descriptor and the named path before and after reading. If a file or an ancestor changes during that observation, its count remains pending rather than associating the read bytes with obsolete metadata. These checks reduce race windows; they are not an atomic filesystem snapshot or a guarantee against every concurrent change.

The line read is capped by the remaining byte allowance. A file that grows after discovery cannot consume an unchecked larger allowance or receive a count under its old source identity. A pending count may clear on a later fresh scan once the file is stable and fits the available budget.

Zero pending syntax checks covers only the supported files reached by that scan. It does not establish that discovery finished, that every recognized language was parsed, or that every line total is complete. Check coverage and line-count completion separately. Because each refresh starts a new walk, repeatedly hitting the same traversal budget does not guarantee eventual coverage of a larger tree; review and narrow explicit roots within the documented limits.

The checked-in example policy and setup revision 2 bundle remain pinned to their released hashes. Their scanner uses its default line budget unless the owner adds `maxLineCountBytes` to a private policy.
