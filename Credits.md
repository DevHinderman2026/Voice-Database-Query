# Voice Database Query credits

Voice Database Query is made by Russell Hinderman and built together with Claude, an AI model made by Anthropic.

## AI-assisted engineering

Voice Database Query was made with AI-assisted engineering. Russell Hinderman designed it: what it does, how it sounds and behaves, and its accessibility rules. He tests it by hand on Windows with NVDA. Claude, an AI model made by Anthropic, wrote the program code, the tests and the documentation under his direction.

Voice Database Query itself is free software under the MIT License (see the LICENSE file). The projects below keep their own licenses.

## Speech recognition

- **Vosk**, offline speech recognition, by Alpha Cephei. Apache License 2.0. <https://alphacephei.com/vosk/>
- **vosk-model-en-us-0.22**, the English speech model, by Alpha Cephei. Apache License 2.0. Downloaded by the installer; not included here.

## Program libraries

- **wxPython**, the window toolkit, also used by NVDA. wxWindows Library Licence. <https://wxpython.org>
- **sounddevice**, microphone input, by Matthias Geier. MIT License. <https://python-sounddevice.readthedocs.io>
- **accessible_output2**, which carries the NVDA controller client used for speech and braille. MIT License.
- **pywin32**, used to talk to JAWS and the Windows voice. Python Software Foundation License.
- **Python** and its built-in **sqlite3** module. Python Software Foundation License.

## Thanks

- The speech module comes from Musician Forge, Russell's accessible digital audio workstation.
- The NBA and movies course databases from 42mcmaster/databaseApplications were the test data during development. They are not included.
