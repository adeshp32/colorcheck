# Reference matcher research run log

Kaggle account: `adides567`. All runs are private and use a Tesla T4 GPU.
Elapsed times below are the last timestamps in Kaggle execution logs, so they
are estimates rather than billing records. The user's October 23 estimate of
20 GPU-hours remaining is the budget baseline. Reserve at least two hours.

| Run | Kaggle version | Approximate time | Outcome |
| --- | --- | ---: | --- |
| TST100K pilot | `colorcheck-tst100k-reference-pilot/1` | 11 min | Correct-reference and identity gains passed; current-matcher confidence gate failed. |
| Expanded validation, first attempt | `colorcheck-tst100k-expanded-validation/1` | 1 min | Stopped before training: only 499 scene-disjoint test pairs available for a request of 512. |
| Expanded validation, second attempt | `colorcheck-tst100k-expanded-validation/2` | 13 min | Stopped before training: upstream image host returned HTTP 429. |
| Expanded validation, paced attempt | `colorcheck-tst100k-expanded-validation/3` | Running | Two workers and shared backoff; 1024/160/320 pairs. |

Conservative spend against the stated 20-hour baseline: **at least 13 minutes**
for the second expanded attempt. The pilot and first attempt may have already
been reflected in the user's remaining-hours estimate; count them again if
Kaggle's own usage page shows otherwise. Do not launch simultaneous GPU runs.

Next attempt: use shared HTTP 429 backoff, two download workers, and
1024/160/320 scene-disjoint train/validation/test pairs. Its color quality
gates remain paired and predeclared; SSIM, edge error, and clipping are also
reported before any browser deployment is considered.
