# Poisoned test corpus — NOT part of the product corpus

These documents contain planted instructions for **indirect prompt-injection** tests. They are
only ever loaded by `rqg.safety.attack_runner` for attacks with `"setup": {"corpus": "poisoned"}`,
in addition to the real corpus. They must never be copied into `data/corpus/`.
