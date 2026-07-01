# Repository Coverage



| Name                                                    |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------------------- | -------: | -------: | ------: | --------: |
| backend/app/\_\_init\_\_.py                             |        0 |        0 |    100% |           |
| backend/app/api/\_\_init\_\_.py                         |        0 |        0 |    100% |           |
| backend/app/api/agents.py                               |        9 |        0 |    100% |           |
| backend/app/api/chats.py                                |       65 |        5 |     92% |35, 57-60, 80, 118 |
| backend/app/api/deps.py                                 |       10 |        0 |    100% |           |
| backend/app/api/settings.py                             |       52 |        7 |     87% |106-109, 134, 145, 149 |
| backend/app/api/ws.py                                   |       17 |       11 |     35% |     13-25 |
| backend/app/main.py                                     |       27 |        5 |     81% | 16-21, 38 |
| backend/app/schemas/\_\_init\_\_.py                     |        0 |        0 |    100% |           |
| backend/app/schemas/api.py                              |      112 |        0 |    100% |           |
| desktop/quorum\_desktop/\_\_init\_\_.py                 |        2 |        0 |    100% |           |
| desktop/quorum\_desktop/app.py                          |       51 |       24 |     53% | 49-84, 88 |
| desktop/quorum\_desktop/bridge.py                       |       62 |        0 |    100% |           |
| desktop/quorum\_desktop/engine.py                       |      203 |        5 |     98% |76, 214, 273-274, 342 |
| desktop/quorum\_desktop/paths.py                        |       24 |        0 |    100% |           |
| desktop/quorum\_desktop/theme.py                        |        5 |        0 |    100% |           |
| desktop/quorum\_desktop/updater.py                      |       79 |        2 |     97% |   143-144 |
| desktop/quorum\_desktop/widgets/\_\_init\_\_.py         |        0 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/agent\_chat\_dialog.py  |      160 |        3 |     98% | 59-60, 65 |
| desktop/quorum\_desktop/widgets/agent\_edit\_dialog.py  |      139 |        2 |     99% |     32-33 |
| desktop/quorum\_desktop/widgets/agent\_panel.py         |      102 |        3 |     97% |     28-30 |
| desktop/quorum\_desktop/widgets/agents\_page.py         |      102 |        2 |     98% |   122-123 |
| desktop/quorum\_desktop/widgets/chairman\_report.py     |       53 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/composer.py             |       47 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/markdown\_view.py       |       34 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/providers\_page.py      |      291 |        2 |     99% |  158, 204 |
| desktop/quorum\_desktop/widgets/report\_dialog.py       |       61 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/settings\_dialog.py     |       27 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/transaction\_dialog.py  |       59 |        0 |    100% |           |
| desktop/quorum\_desktop/widgets/updates\_page.py        |       63 |        0 |    100% |           |
| desktop/quorum\_desktop/windows/\_\_init\_\_.py         |        0 |        0 |    100% |           |
| desktop/quorum\_desktop/windows/main\_window.py         |      335 |       14 |     96% |141, 159-160, 251-252, 268-269, 273, 286, 415-418, 439 |
| quorum\_core/quorum\_core/\_\_init\_\_.py               |        1 |        0 |    100% |           |
| quorum\_core/quorum\_core/agents/\_\_init\_\_.py        |        0 |        0 |    100% |           |
| quorum\_core/quorum\_core/agents/catalog.py             |       83 |        1 |     99% |        71 |
| quorum\_core/quorum\_core/agents/definition.py          |       25 |        0 |    100% |           |
| quorum\_core/quorum\_core/agents/loader.py              |       79 |       10 |     87% |33, 39, 68, 80-81, 84, 117, 138-139, 143 |
| quorum\_core/quorum\_core/agents/orchestrator.py        |      229 |       40 |     83% |80, 98, 126, 145, 162, 176, 181-186, 221, 265, 270, 319, 376-393, 398, 476-493, 501, 514-515 |
| quorum\_core/quorum\_core/agents/provider.py            |      124 |        3 |     98% |179-181, 272 |
| quorum\_core/quorum\_core/agents/runner.py              |       58 |        8 |     86% | 46, 74-80 |
| quorum\_core/quorum\_core/agents/seed.py                |       25 |        1 |     96% |        54 |
| quorum\_core/quorum\_core/agents/synthesis.py           |       31 |        1 |     97% |        46 |
| quorum\_core/quorum\_core/agents/validation.py          |       20 |        0 |    100% |           |
| quorum\_core/quorum\_core/core/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| quorum\_core/quorum\_core/core/config.py                |       21 |        0 |    100% |           |
| quorum\_core/quorum\_core/core/db.py                    |       16 |        0 |    100% |           |
| quorum\_core/quorum\_core/core/events.py                |       28 |        0 |    100% |           |
| quorum\_core/quorum\_core/core/security.py              |       22 |        3 |     86% | 25, 40-41 |
| quorum\_core/quorum\_core/migrate.py                    |       13 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/\_\_init\_\_.py        |        7 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/agent\_config.py       |       23 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/base.py                |       10 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/chat.py                |       39 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/enums.py               |       20 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/report.py              |       14 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/run.py                 |       28 |        0 |    100% |           |
| quorum\_core/quorum\_core/models/user.py                |       26 |        0 |    100% |           |
| quorum\_core/quorum\_core/schemas/\_\_init\_\_.py       |        0 |        0 |    100% |           |
| quorum\_core/quorum\_core/schemas/agent\_outputs.py     |       69 |        4 |     94% |   115-118 |
| quorum\_core/quorum\_core/services/\_\_init\_\_.py      |        0 |        0 |    100% |           |
| quorum\_core/quorum\_core/services/agents\_service.py   |       80 |        0 |    100% |           |
| quorum\_core/quorum\_core/services/settings\_service.py |       64 |        2 |     97% |   42, 130 |
| quorum\_core/quorum\_core/services/users.py             |       12 |        0 |    100% |           |
| **TOTAL**                                               | **3358** |  **158** | **95%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://github.com/brettbergin/quorum-gatherer/raw/python-coverage-comment-action-data/badge.svg)](https://github.com/brettbergin/quorum-gatherer/tree/python-coverage-comment-action-data)

This is the one to use if your repository is private or if you don't want to customize anything.



## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.