{
  description = "pfun-cma-engine-c: C library, demos, and Python/TS tooling";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
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

        # Browser wasm demo (`make demo-wasm`): index-wasm.html + demo-wasm.{js,wasm}.
        demo-wasm = pkgs.stdenv.mkDerivation {
          pname = "pfun-cma-engine-demo-wasm";
          version = "0.1.3";
          src = pkgs.lib.cleanSource ./.;
          nativeBuildInputs = [
            pkgs.emscripten
            pkgs.gnumake
          ];
          buildPhase = ''
            runHook preBuild
            # emscripten needs a writable cache inside the sandbox
            export EM_CACHE=$TMPDIR/emscripten_cache
            export HOME=$TMPDIR
            mkdir -p public
            make demo-wasm
            runHook postBuild
          '';
          installPhase = ''
            runHook preInstall
            mkdir -p $out/share/pfun-cma-engine/demo-wasm
            cp public/index-wasm.html public/demo-wasm.js public/demo-wasm.wasm \
              $out/share/pfun-cma-engine/demo-wasm/
            runHook postInstall
          '';
        };
        default = pfun-cma-engine;
      });

      # `nix run .#serve-wasm [port]` serves the wasm demo over http (default 8000).
      apps = forAllSystems (
        pkgs:
        let
          serve = pkgs.writeShellScript "serve-wasm" ''
            port="''${1:-8000}"
            dir=${self.packages.${pkgs.system}.demo-wasm}/share/pfun-cma-engine/demo-wasm
            echo "Serving $dir at http://localhost:$port/index-wasm.html"
            exec ${pkgs.python3}/bin/python3 -m http.server "$port" --directory "$dir"
          '';
        in
        rec {
          serve-wasm = {
            type = "app";
            program = "${serve}";
          };
          default = serve-wasm;
        }
      );

      # Emscripten is only downloaded/built when explicitly requested:
      #   nix develop          -> no emscripten (native C/Python/TS work)
      #   nix develop .#wasm   -> adds emscripten (needed for `make demo-wasm`)
      #   nix build .#demo-wasm / nix run .#serve-wasm pull it in as a build dep
      devShells = forAllSystems (
        pkgs:
        let
          mkDevShell =
            {
              withWasm ? false,
            }:
            pkgs.mkShell {
              packages =
                with pkgs;
                [
                  # C toolchain
                  gcc
                  gnumake
                  pkg-config
                  clang-tools
                  gsl
                  # LLVM IR analysis targets (opt, llc, FileCheck)
                  llvmPackages.clang
                  llvmPackages.llvm
                  # Python (uv manages the venv) and TypeScript demo
                  python311
                  uv
                  nodejs_22
                ]
                ++ pkgs.lib.optionals withWasm [ pkgs.emscripten ];

              shellHook = ''
                # The Makefile hardcodes UV := /usr/bin/uv; use the shell's uv.
                export MAKEFLAGS="UV=$(command -v uv) $MAKEFLAGS"
                export UV_PYTHON_DOWNLOADS=never
                export UV_PYTHON="${pkgs.python311}/bin/python"
                export EM_CACHE="''${EM_CACHE:-$PWD/.emscripten_cache}"
                [ -d .venv ] || uv sync --dev
              ''
              + pkgs.lib.optionalString (!withWasm) ''
                command -v emcc >/dev/null && \
                  echo "build-wasm:\t\t'nix build .#build-wasm'\nserve-wasm:\t\t'nix run .#serve-wasm [port:8080]'" || \
                  echo "note: emscripten not loaded; run 'nix develop .#wasm' for wasm builds"
              '';
            };
        in
        {
          default = mkDevShell { };
          wasm = mkDevShell { withWasm = true; };
        }
      );
    };
}
