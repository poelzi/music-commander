{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    spec-kitty = {
      url = "github:poelzi/spec-kitty/nix-flake";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      spec-kitty,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;

        # Runtime dependencies
        pythonDeps =
          ps: with ps; [
            click
            jinja2
            lark
            rich
            sqlalchemy
            tomli-w
          ];

        # Development dependencies
        devDeps =
          ps: with ps; [
            pytest
            pytest-cov
            mypy
            ruff
            mutagen
          ];

        # Python environment for music-commander (runtime deps only)
        python-music-cmd = pkgs.writeShellScriptBin "python-music-cmd" ''
          exec ${python.withPackages pythonDeps}/bin/python "$@"
        '';

        # Full dev environment with all deps
        pythonEnv = python.withPackages (ps: (pythonDeps ps) ++ (devDeps ps));

      in
      {
        packages.default = python.pkgs.buildPythonApplication {
          pname = "music-commander";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";

          nativeBuildInputs = with python.pkgs; [
            setuptools
          ];

          propagatedBuildInputs = pythonDeps python.pkgs;

          # Skip tests during build (run via checks)
          doCheck = false;

          # Install default config file
          postInstall = ''
            mkdir -p $out/share/music-commander
            cp ${./config.example.toml} $out/share/music-commander/config.example.toml
          '';
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            python-music-cmd
            pkgs.git-annex
            pkgs.ffmpeg
            spec-kitty.packages.${system}.default
          ];

          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };

        checks.default =
          pkgs.runCommand "pytest"
            {
              buildInputs = [ pythonEnv ];
            }
            ''
              cd ${./.}
              pytest --tb=short
              touch $out
            '';
      }
    );
}
