# Example

`input/v1` is a small library and its README. `input/v2` is the next commit: defaults, a parameter name and a
constant changed, a function was removed, and only the `chunk` line of the README was updated.

Run it (from the project root, with Ollama running for Gemma explanations):

    bash examples/run_example.sh

Expected result in `output/`: 4 confirmed and 1 potential finding. The `chunk` line (docs updated with the
code) and the private `_clean` helper produce no finding.
