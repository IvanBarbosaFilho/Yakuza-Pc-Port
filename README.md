<div align="center">

# Yakuza — PC Port

**English** · [Português (Brasil)](README.pt-BR.md)

**Yakuza (PS2) running natively on Windows: 60 FPS, high resolution, over-the-shoulder camera, keyboard and mouse.**

![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6?logo=windows&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-d9261c)
![Status](https://img.shields.io/badge/status-beta-yellowgreen)
![Based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

### [⬇ Download the latest release](../../releases/latest)

</div>

---

> [!IMPORTANT]
> The game is **not included**. You need **your own copy** of Yakuza for the PS2 (USA, `SLUS-21348`) as a disc
> image (`.iso`).

## What is this?

A PC port of *Yakuza* made by **static recompilation**: the game's PS2 code was translated into C++ and compiled as a
Windows program, instead of being emulated. The graphics use PCSX2's renderer (DirectX 11), so you get high internal
resolutions and a sharp picture.

- 60 FPS (or the original 30), switchable in game
- 1x to 4x internal resolution; 4:3, 16:9 or stretched picture
- **Over-the-shoulder camera** (optional): right stick or mouse turns it; talks, events and Heat Actions keep the game's
  own cameras
- Keyboard and mouse (mouse buttons attack / grab), Xbox, PlayStation and other controllers
- Fullscreen (F11), memory card saves next to the game

## Download and play

### Windows

1. Download the ZIP from the [**latest release**](../../releases/latest) and extract it anywhere.
2. Open **`Yakuza.exe`**.
3. The first time, pick your Yakuza disc image (`.iso`). The game checks it is the right one and remembers it
   (in `Yakuza.ini`): from then on, just open `Yakuza.exe`.

If you move the `.iso`, the game asks for it again. Saves are in `memcard0.ps2`, options in `config\mods.ini`, and
each session writes `logs\play.log` (attach it when you report a problem).

### Requirements

- Windows 10 or 11, 64-bit, and a DirectX 11 graphics card
- A processor with SSE4.1 (any PC from the last ~12 years)

## Options

**F2** on the keyboard or **L3** on the controller opens the options menu while playing:

| Option | |
|---|---|
| Frame rate | 30 / 60 FPS |
| Internal resolution | 1x to 4x |
| Aspect ratio | 4:3, 16:9, fill the window |
| Over-the-shoulder camera | on / off, mouse camera, mouse sensitivity |
| Fullscreen | also F11 |

## Controls

| PS2 | Keyboard / mouse |
|---|---|
| Left stick | W A S D |
| D-pad | Arrow keys |
| ✕ | Space / K |
| ○ | E / L / right mouse button |
| □ | J / left mouse button |
| △ | I / F / middle mouse button |
| L1 / R1 | Left Ctrl / Left Shift |
| L2 / R2 | Z / C |
| L3 / R3 | G / V |
| START / SELECT | Enter / Tab |

With the over-the-shoulder camera on, the mouse turns the camera. Controllers work out of the box; for an unusual one,
put a `gamecontrollerdb.txt` ([SDL GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB)) next to
`Yakuza.exe`.

| Key | In game |
|---|---|
| F2 | Options menu |
| F11 | Fullscreen / window |

## Known issues

- Beta: the game can be played from the start, but not every chapter has been tested yet. Please report what you find
  with your `logs\play.log`.

## Build from source

The Windows package is cross-compiled from Linux (Nix) with clang-cl and the MSVC CRT / Windows SDK unpacked by
[xwin](https://github.com/Jake-Shadle/xwin); no Windows machine is needed. You need your own disc image to generate the
game code.

1. The runtime and recompiler: [PS2Recomp](https://github.com/ran-j/PS2Recomp) with this project's changes
   (`PS2Recomp-main`), including the Windows toolchain `cmake/clang-cl-xwin.cmake`.
2. The game code: `./nixsh ./pipeline.sh` in this folder (extract, analyze, recompile; `config/` holds the
   game-specific settings, `mods/` the over-the-shoulder camera).
3. PCSX2's GS for Windows: `thirdparty/pcsx2-gs` built with the same toolchain into `pcsx2gs.dll`.
4. The game for Windows: the same CMake build with `-DCMAKE_TOOLCHAIN_FILE=cmake/clang-cl-xwin.cmake`, then
   `tools/package_windows.sh` makes `dist/Yakuza-win64.zip`.

## Credits

- Made by **Ivan Barbosa Filho**
- [PS2Recomp](https://github.com/ran-j/PS2Recomp) (recompiler and runtime), [PCSX2](https://pcsx2.net/) (GS renderer),
  the [Urban Reign PC port](https://github.com/thiagordsfx) by **thiagordsfx** (the PCSX2 GS bridge this port uses),
  [SDL GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB).
- *Yakuza* © SEGA. This is a fan project, not affiliated with or endorsed by SEGA. No game content is distributed.

The code in this repository is released under the **GPL-3.0** license. See [`LICENSE`](LICENSE).
