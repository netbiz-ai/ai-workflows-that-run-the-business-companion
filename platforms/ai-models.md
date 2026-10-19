# AI model prices behind the cost lines

Checked 2026-10-12.

The recipes call low-cost models for bounded AI steps.
These are the per-million-token prices (input / output) the book's cost lines use, as of October 2026.

| Model | Input / output per million tokens | Notes |
|---|---|---|
| Claude Haiku 5.5 (Anthropic) | $0.10 / $0.50 up to 100,000 tokens | Described for classification, extraction and routing; US-only inference costs 1.1x |
| Claude Sonnet 5.5 (Anthropic) | $2 / $10 | Batch API halves input and output prices |
| GPT-6 Luna (OpenAI) | $0.10 / $0.50 | Batch halves the price, with a 24-hour turnaround |
| GPT-5 nano (OpenAI) | $0.05 / $0.40 | Still listed |
| Gemini 3.1 Flash-Lite (Google) | $0.25 / $1.50 | Output includes thinking tokens |

Token counts drive these costs.
For Anthropic's current tokenizer, 1 million tokens is roughly 555,000 words, about 1.8 tokens a word; for Gemini, a token is about 4 characters.
A model can change behavior behind an unchanged name, which is why the golden set is rerun on a schedule (book Chapter 17).

## Source

*AI Workflows That Run the Business*, Appendix B.
