# pfun-health/pfun-cma-engine-c

_Optimized C extensions for PFun CMA model (numerical engine)._

## Usage

[Python Demo Source](demo.py)

See [BUILD.md](BUILD.md) for build instructions.

## Usage `&` Development

### Install uv

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install development dependencies

##
	# include dev deps
    $ uv sync --dev

### Run demo

##
	# run interactively with ipython
	$ uv run ipython -i -- ./demo.py
