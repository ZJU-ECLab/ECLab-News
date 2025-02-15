{
  inputs = {
    systems.url = "github:nix-systems/default";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    {
      self,
      nixpkgs,
      systems,
    }:
    let
      forEachSystem =
        f: nixpkgs.lib.genAttrs (import systems) (system: f { pkgs = import nixpkgs { inherit system; }; });
    in
    {
      devShells = forEachSystem (
        { pkgs }:
        {
          default =
            let
              packageOverrides = pkgs.callPackage ./python-packages.nix { };
              python = pkgs.python312.override { inherit packageOverrides; };
            in
            pkgs.mkShellNoCC {
              buildInputs = [
                (python.withPackages (
                  ps: with ps; [
                    proces
                    pandas
                    openpyxl
                  ]
                ))
              ];
              shellHook = ''
                fish
              '';
            };
        }
      );
    };
}
