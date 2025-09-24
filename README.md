## File Tree Builder – Quick Start

Generate a Markdown file tree with file contents using a simple TUI (text-based UI).

### 🚀 Quick Start - Docker Compose

If you have Docker and Docker Compose installed:

- copy the `docker-compose.yml` inside the folder where you want to extract the file contents from
- the cd into the same. directory from the terminal and run

  ```bash
  docker compose run --rm tui
  ```

- This launches the file tree selector inside your current directory.

### 🐳 Run Without the Docker Compose file (little setup required)

You can add a small Shell Function to your shell configuration file

- on `MAC` or `Linux` e.g. add this to your ~/.zshrc:

  ```
  ftree() {
  docker run --rm -it \
      -v "$(pwd)":/data \
      -w /data \
      --user "$(id -u):$(id -g)" \
      -e TERM -e COLORTERM \
      -e OUTPUT="${OUTPUT:-FILETREE.md}" \
      -e EXCLUDES="${EXCLUDES:-.git,node_modules,__pycache__}" \
      ghcr.io/fedor98/file_tree_builder_tui:${FILETREE_TAG:-latest} "$@"
  }
  ```

- on `Windows` you can add it to your PowerShell

  - ‼️ haven't tested it, so don't know if it will work without any modification

  ```
  function ftree {
      docker run --rm -it `
      -v "${PWD}:/data" `
      -w /data `
      -e TERM -e COLORTERM `
      -e OUTPUT=${env:OUTPUT} `
      -e EXCLUDES=${env:EXCLUDES} `
      ghcr.io/fedor98/file_tree_builder_tui:latest $args
  }
  ```

- then restart restart/reload your Shell or simply a new one
- by calling `ftree` you will start the TUI in your current directory

### 🧭 How It Works

1. **First screen**: Navigate and toggle files/folders to include/exclude.

- `Space` → select/unselect
- `Enter` → expand/collapse folders
- `a` → select all
- `n` → select none
- `g` → generate Markdown output

2. **Second screen**: Confirms whether unselected files should still appear in the tree.
3. **Result**: A FILETREE.md (or your custom OUTPUT) file is created with the tree and selected file contents.
