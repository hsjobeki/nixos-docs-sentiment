{
  description = "Reproducible sentiment analysis of NixOS documentation feedback";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        py = pkgs.python3;

        # stdlib-only application: nothing outside the pinned interpreter is
        # pulled in, so the whole toolchain is fixed by flake.lock.
        app = py.pkgs.buildPythonApplication {
          pname = "nixdoc-sentiment";
          version = "0.1.0";
          src = ./.;
          pyproject = true;
          build-system = [ py.pkgs.setuptools ];
          dependencies = [ ]; # intentionally empty: stdlib only
          nativeCheckInputs = [ ];
          # Classifier is deterministic and offline; tests never hit the network.
          checkPhase = ''
            runHook preCheck
            ${py.interpreter} -m unittest discover -s tests -v
            runHook postCheck
          '';
        };
      in {
        packages.default = app;
        packages.nixdoc-sentiment = app;

        apps.default = {
          type = "app";
          program = "${app}/bin/nixdoc-sentiment";
          meta.description = "Run the NixOS documentation sentiment pipeline";
        };

        devShells.default = pkgs.mkShell {
          packages = [ py ];
          shellHook = ''
            echo "nixdoc-sentiment devshell: python ${py.version} (stdlib only)"
            echo "run: python -m nixdoc_sentiment run --help"
          '';
        };
      });
}
