{ pkgs, lib, config, inputs, ... }:

{
  packages = [
    pkgs.git
    pkgs.gnumake
    pkgs.gcc
    pkgs.pkg-config
  ];

  languages.python = {
    enable = true;
    package = pkgs.python311;
    venv.enable = true;
    uv = {
      enable = true;
      sync.enable = true;
      sync.allGroups = true;
    };
  };

  languages.c.enable = true;

  enterShell = ''
    python --version
    gcc --version | head -1
  '';

  enterTest = ''
    pytest
  '';
}
