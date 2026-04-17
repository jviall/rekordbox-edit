# Contributing to Rekordbox Bulk Edit

Thanks for your interest in contributing to this project! Python is not my expertise, so I'm eager for those more seasoned than I to weigh in. One way or another, I hope you're here as a fellow DJ looking to make managing a RekordBox library easier :)

## Development Setup

### Prerequisites

- Python 3.10+
- [UV](https://docs.astral.sh/uv/) for dependency management

### Installation

1. **Install UV**:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/jviall/rekordbox-bulk-edit.git
   cd rekordbox-bulk-edit
   ```

3. **Install the project and dependencies**:

   ```bash
   uv sync
   ```

4. **Activate the virtual environment**:

   ```bash
   source .venv/bin/activate    # macOS/Linux
   ```

   _or_

   ```Powershell
   .venv\Scripts\activate       # Windows
   ```

5. Install `pre-commit` hooks

   ```bash
   pre-commit install
   ```

6. **Verify installation**:
   ```bash
   rekordbox-bulk-edit --version
   ```

### Tasks (via Make)

```bash
# Run tests
make test

# Run tests with coverage
make coverage

# Run linting and type-checking, will auto-fix issues
make lint

# Run formatting
make format

# Run all pre-commit hooks on all files
make run-hooks
```

## Commit Convention

This project uses and enforces [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). The allowable types of commits are:

- `BREAKING`: introduces breaking changes (major bump)
- `feat`: introduces new features (minor bump)
- `fix`: patches a bug, upgrades a dependency (minor bump)

- `refactor`: code refactor with no functionality changes (minor bump)

- `ci`: only CI/CD changes
- `test`: only adds or modifies tests
- `docs`: only documentation changes
- `chore`: some other non-code changes such as configs or dev-dependency updates
