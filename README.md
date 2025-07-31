# KOTTE - Kanji Oriented Tiny Text Editor
A compact full-screen text editor implemented
in a single Python file (~520 lines).
Demonstrates practical handling of multibyte, multiwidth
Japanese/English mixed text in a terminal environment.

It's compact enough that you might actually want to read
the source code, right? :-)

*No setup, no install — just grab it and go.*

Designed as a minimal yet realistic implementation
that will evolve into xtte (extensible tiny text editor),
a Python module for building full-screen editors.

## Status
Version 1.0b1 (Beta) – Core features are in place, testing in progress.

## Features
* Handles multibyte, multiwidth characters correctly (yes, Japanese Kanji included!)
* Lets you edit mixed Japanese/English text without breaking layout
* Basic but essential editing: insert, delete, search, move around with the cursor
* Small codebase (~520 lines) so you can actually read it without a headache
* Runs in your terminal with just Python and curses

## Usage
### Grab the file and run it:

```bash
git clone https://github.com/iigura/kotte.git
cd kotte
python3 kotte.py [targetFile]
```

- If you don’t specify a file, it just starts with an empty buffer.
- If you specify `targetFile`, it opens it for editing.

### Basic controls:
- Cursor movement: arrow keys (or `h/j/k/l`), `0` to jump to line start, `$` to jump to line end
- Scroll: `Ctrl-E` / `Ctrl-Y`, Page scroll: `Ctrl-U` / `Ctrl-D`
- Move by word: `w` forward, `b` backward
- Jump to top/bottom: `g` / `G`, screen top/bottom: `H` / `L`
- Insert mode: `i` (before), `a` (after), `o` (new line below), `O` (new line above)
- Replace: `r`, delete: `x`, join lines: `J`
- Visual select: `v`
- 2-stroke commands: `dd` (delete line), `zz` (center current line), `ZZ` (save and quit)
- Search: `/` to set pattern, `n` for next match, `N` for previous match
- Command line: `:`

*If you know vim, you’ll feel at home — most of this will make
sense right away.*  

Colon commands are supported as well and are explained
in the next section.

### Colon commands:
Currently implemented colon commands are:

- `:q` — quit safely (prevents accidental loss)
- `:q!` — quit without saving
- `:w` — save the current file
- `:wq` — save and quit
- `:e <file>` — load another file

These are intentionally close to vim so you don’t have to
learn new muscle memory.

## Requirements
- Python 3.x
- curses library (available on Unix-like systems)

## License
MIT License

## Acknowledgements
KOTTE was greatly inspired by **ae**,
the ultra-compact full-screen text editor  
created by Anthony and winner of the
*International Obfuscated C Code Contest (IOCCC)*.
Without ae, KOTTE wouldn’t exist — huge thanks!

---
*The code is short — take a look inside!*

