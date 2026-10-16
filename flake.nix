{
  description = "pfun-cma-engine-c: C library, demos, and Python/TS tooling";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        # Shared + static C library (`make libs`), plus public headers.
        pfun-cma-engine = pkgs.stdenv.mkDerivation {
          pname = "pfun-cma-engine-c";
          version = "0.1.3";
          src = pkgs.lib.cleanSource ./.;
          buildFlags = [ "libs" ];
          installPhase = ''
            runHook preInstall
            install -Dm755 pfun_cma_engine/libpfun_cma_engine.so -t $out/lib
            install -Dm644 pfun_cma_engine/libpfun_cma_engine.a -t $out/lib
            mkdir -p $out/include
            cp -r include/pfun_cma_engine $out/include/
            runHook postInstall
          '';
        };
        default = pfun-cma-engine;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            # C toolchain
            gcc gnumake pkg-config clang-tools gsl
            # LLVM IR analysis targets (opt, llc, FileCheck)
            llvmPackages.clang llvmPackages.llvm
            # wasm demo (`make demo-wasm`)
            emscripten
            # Python (uv manages the venv) and TypeScript demo
            python311 uv nodejs_22
          ];

          shellHook = ''
            # The Makefile hardcodes UV := /usr/bin/uv; use the shell's uv.
            export MAKEFLAGS="UV=$(command -v uv) $MAKEFLAGS"
            export UV_PYTHON_DOWNLOADS=never
            export UV_PYTHON="${pkgs.python311}/bin/python"
            export EM_CACHE="''${EM_CACHE:-$PWD/.emscripten_cache}"
            [ -d .venv ] || uv sync --dev
          '';
        };
      });
    };
}
