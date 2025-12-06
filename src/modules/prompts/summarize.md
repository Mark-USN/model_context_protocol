---
name: summarize_text
description: Summarize arbitrary input text.
tags:
  - public
  - summarize
style: bullets

params:
  text:
    description: The text to summarize
    required: true
  lang:
    description: Output language
    required: false
    default: en
    type: string
---

Please summarize the following text in 3–5 bullet points.
Respond in {lang}.

{text}
