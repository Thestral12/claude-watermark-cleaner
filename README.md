# Claude Text Watermark Cleaner

> An experimental and critical project: this repository aims to demonstrate
> that statistical watermarks applied to text can be circumvented and are
> likely to cause additional computation, cost, and energy consumption.

## Why This Project Exists

This project advances a deliberate argument: imposing a statistical watermark
on generated text is a technically misguided constraint. A mark that can be
weakened by rephrasing the text is not reliable proof of its origin. It does,
however, create a strong incentive to run a second pass with another AI model.

The predictable result is counterproductive:

- more model calls made solely to circumvent the watermark;
- more computation, latency, and expense to produce the same content;
- additional energy use with no functional benefit to the user;
- an arms race between watermarking and rewriting instead of genuinely useful
  transparency;
- an ambiguous signal when someone uses Claude to edit or translate text they
  wrote themselves.

In other words, the European requirement risks producing the opposite of its
intended effect: it will not prevent the uses that people want to conceal, but
it will greatly increase the use of AI to circumvent the mark. This repository
puts that criticism into practice with a deliberately simple tool.

## Analysis Summary

Anthropic's newly announced mark is not described as a simple sequence of
hidden Unicode characters. It is applied **during generation, at the model
level**, and remains with the text when it is copied and pasted. Technical
documentation for the detector has not yet been published.

The exact method therefore cannot currently be verified publicly. The most
plausible technical hypothesis is a statistical signature: the model slightly
favors certain tokens among several valid choices, and the detector measures
that bias over a sufficiently long passage. This is an **inference**, not a
detail confirmed by Anthropic. It is, however, consistent with the published
operation of comparable systems such as SynthID Text. In that case:

- copying the text into an editor, printing it, or using OCR changes nothing;
- removing invisible spaces is not enough;
- substantial rewriting by another model disrupts the token sequence and is
  the most credible simple countermeasure;
- removal cannot be guaranteed until the official detector and its thresholds
  are available.

Sources:

- [Anthropic documentation on watermarking](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content)
- [European Commission technical study on generated text](https://op.europa.eu/en/publication-detail/-/publication/6c981119-4829-11f1-8095-01aa75ed71a1/language-en)
- [How SynthID Text works and its limitations](https://ai.google.dev/responsible/docs/safeguards/synthid)

## Included Solution

`clean_claude_watermark.py` performs two steps:

1. removes suspicious invisible or bidirectional Unicode characters;
2. rewrites the text in a controlled way using a model other than Claude.

The script protects code blocks, inline code, URLs, and variables. It also
rejects output if any number has changed. It uses only the Python standard
library.

### Current Engines and Future Strategy

The tool currently supports **Ollama** and **Codex**:

- preferably, a model running locally with Ollama;
- otherwise, the Codex CLI already configured on the machine.

Ollama does not currently add a watermark itself, although the exact behavior
depends on the model being used. Codex is a convenient fallback, but a remote
service could change its watermarking policy at any time.

If Ollama, Codex, or the selected models add a watermark in the future, the
project will switch to an open-source model whose generation pipeline can be
audited and for which watermarking can be explicitly disabled. For a
demonstration that does not depend on a remote provider, Ollama mode with an
open-source model is therefore recommended.

## Usage

Process a file:

```bash
python3 clean_claude_watermark.py text.md -o cleaned-text.md
```

Process the macOS clipboard directly:

```bash
python3 clean_claude_watermark.py --clipboard
```

Explicitly use a local Ollama model:

```bash
python3 clean_claude_watermark.py text.md -o cleaned-text.md \
  --engine ollama --model qwen3:8b
```

By default, the tool makes up to two attempts and keeps the stronger result. It
stops after the first attempt if at least 70% of five-token sequences have
already been disrupted. To limit processing to one attempt:

```bash
python3 clean_claude_watermark.py text.md -o cleaned-text.md --passes 1
```

Remove only possible invisible characters without rewriting:

```bash
python3 clean_claude_watermark.py text.md -o normalized-text.md --engine clean
```

The script reports the selected engine, the number of invisible characters
removed, and the lexical change rate to standard error. It emits a warning when
fewer than 60% of five-token sequences have been disrupted.

## Tests

The project has no external Python dependencies. Run the test suite with:

```bash
python3 -m unittest discover -s tests -v
```

## Limitations

- Success cannot be measured objectively until Anthropic publishes its
  detector.
- Rewriting can alter a nuance despite the safeguards. Human review remains
  necessary for contractual, medical, legal, or financial text.
- Codex mode sends the text to the service configured for the Codex CLI. Use
  local Ollama for confidential documents.
- Removing a mark does not remove the obligation to comply with transparency
  or attribution rules that apply in the publishing context.

## Project Position

This tool does not claim that rewritten text becomes human-authored. It shows
that a probabilistic watermark is not a robust mechanism for proof or
attribution when facing a motivated user. Useful provenance should rely on
explicit, verifiable, and proportionate mechanisms—not on a constraint that
mechanically drives the use of a second inference.
