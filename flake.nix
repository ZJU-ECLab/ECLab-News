{
  inputs = {
    systems.url = "github:nix-systems/default";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    {
      nixpkgs,
      systems,
      ...
    }:
    let
      forEachSystem =
        f: nixpkgs.lib.genAttrs (import systems) (system: f { pkgs = import nixpkgs { inherit system; }; });
    in
    {
      devShells = forEachSystem (
        { pkgs }:
        {
          default = pkgs.mkShellNoCC {
            packages = [
              pkgs.python312
              pkgs.uv
              pkgs.ruff
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ];
            shellHook = ''
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.zlib
              ]}:$LD_LIBRARY_PATH"
              echo "Run: uv sync --extra dev"
            '';
          };
        }
      );
    };
}
