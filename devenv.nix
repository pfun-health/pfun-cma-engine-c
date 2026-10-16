{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  packages = [
    pkgs.git
    pkgs.gnumake
    pkgs.gcc
    pkgs.pkg-config
    pkgs.gsl
  ];

  # languages.python = {
  #   enable = true;
  #   package = pkgs.python311;
  #   venv.enable = true;
  #   uv = {
  #     enable = false;
  #   };
  # };

  languages.c.enable = true;

  enterShell = ''
    echo "# pfun-cma-engine-c devenv shell..."
    echo "-----------------------------------"
    python --version
    gcc --version | head -1
    echo "==================================="
    make clean all
    echo "-----------------------------------"
    make
  '';

  enterTest = ''
    uv run pytest
  '';
}
