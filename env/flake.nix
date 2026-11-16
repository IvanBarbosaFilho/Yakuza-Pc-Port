{
  description = "Silent Hill 3 (SLUS-206.22) PS2Recomp workspace";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      # PS2 Emotion Engine support for Ghidra (R5900 MMI, VU macro, LQ/SQ, EE ELF relocations).
      emotionengine = pkgs.ghidra-extensions.buildGhidraExtension (finalAttrs: {
        pname = "ghidra-emotionengine-reloaded";
        version = "2.1.38";
        src = pkgs.fetchFromGitHub {
          owner = "chaoticgd";
          repo = "ghidra-emotionengine-reloaded";
          rev = "v${finalAttrs.version}";
          hash = "sha256-bVUxqjW3cZFpHqbjYtbgF+3YP59y4egcH3EUQSt6zlg=";
        };
        # Ghidra compiles SLEIGH specs lazily into the extension dir, which is read-only in
        # the store, so build r5900.sla ahead of time.
        postInstall = ''
          export HOME=$TMPDIR
          ${pkgs.ghidra}/bin/ghidra-sleigh -a \
            $out/lib/ghidra/Ghidra/Extensions/ghidra-emotionengine-reloaded/data/languages
        '';
        meta.license = pkgs.lib.licenses.asl20;
      });

      ghidra = pkgs.ghidra.withExtensions (_: [ emotionengine ]);
    in
    {
      packages.${system} = {
        inherit ghidra emotionengine;
        default = ghidra;
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          ghidra
          cmake
          ninja
          ccache # pipeline build: unchanged generated files are not recompiled
          mold
          rsync
          perf
          gdb # hardware watchpoints on runtime state (tools that catch host-side overwrites)
          pkg-config
          git
          python3
          binutils
          p7zip
          ffmpeg
          libGL
          libx11
          libxrandr
          libxinerama
          libxcursor
          libxi
          libxext
          vulkan-loader # paraLLEl-GS (Vulkan GS backend) loads libvulkan.so.1 at run time
          libpng # PCSX2 GS library (thirdparty/pcsx2-gs): texture replacement PNGs
          shaderc # PCSX2 GS (Vulkan) loads libshaderc_shared.so.1 at run time to compile its shaders
        ];
        # LD_LIBRARY_PATH for the runner when PS2X_GS=parallel.
        PS2X_VULKAN_LIB = "${pkgs.vulkan-loader}/lib";
        # LD_LIBRARY_PATH for the runner when PS2X_GS=pcsx2 (libpcsx2gs.so compiles its Vulkan shaders with shaderc).
        PS2X_SHADERC_LIB = "${pkgs.shaderc.lib}/lib";
        # Sound: raylib's miniaudio loads libpulse / libasound at run time; without them on the library path it
        # falls back to its Null backend (no sound at all). PulseAudio first (PipeWire serves it), then ALSA.
        PS2X_AUDIO_LIB = "${pkgs.libpulseaudio}/lib:${pkgs.alsa-lib}/lib";
        GHIDRA_INSTALL_DIR = "${ghidra}/lib/ghidra";
      };
    };
}
