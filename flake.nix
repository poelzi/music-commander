{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;

        # Runtime dependencies
        pythonDeps = ps: with ps; [
          click
          rich
          sqlalchemy
          tomli-w
        ];

        # Development dependencies
        devDeps = ps: with ps; [
          pytest
          pytest-cov
          mypy
          ruff
        ];

        pythonEnv = python.withPackages (ps: (pythonDeps ps) ++ (devDeps ps));

      in {
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
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.git-annex
          ];

          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };

        checks.default = pkgs.runCommand "pytest" {
          buildInputs = [ pythonEnv ];
        } ''
          cd ${./.}
          pytest --tb=short
          touch $out
        '';
      });
}
