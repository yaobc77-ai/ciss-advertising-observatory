# X 原始字段清单与接线缺口（2026-10-15）

## 一、数据来源

`.runtime/social_archive_20261005/records.jsonl` 的 `raw.source_row`，共 37,082 个原始行（36,182 个唯一帖子 URL）。下表的数量按原始行计，包含同一帖子的重复行。只读统计，没有改数据。

## 二、现在接入了什么

- 每个原始行都原样存进记录的 `raw.source_row`，所以下列字段都在数据库里，但多数只是原始 JSON，没有字段、索引或图谱关系。
- 检索（关键词、向量段落）只索引 `post_text`。图片文字、音频文字、被引用帖文字、链接说明都不进检索。
- 图谱的 `SocialPost` 只有：`posted_by` → `Account`（取自 `channel.name`）、`source_lists_affiliation` → `SponsorCandidate`（取自 `parent_entity`）、原帖链接、Junkipedia 存档链接、文本版本。原始行里的其他内容都没进图谱。
- 账号身份用的是显示名 `channel.name`（332 个），没有用稳定的 `channel_id`（335 个）或 `channel.username`（334 个）。显示名可能改名或重名。

## 三、字段清单

| 字段 | 有值的原始行 | 类型／取值 | 现在用途 | 图谱 |
|---|---:|---|---|---|
| `post_text` | 37,082 | 文本 | 正文、检索、引用 | TextVersion |
| `date_time.published_at` | 37,082 | 时间戳 | 转为 UTC 日期，日期筛选 | 节点属性 |
| `date_time.created_at`／`modified_at` | 37,082 | 时间戳 | 未用；含义没有文档，不能代替发布时间 | 无 |
| `channel.name` | 37,082 | 显示名 | 账号筛选、Account 节点 | Account |
| `channel_id`／`channel.username`／`channel.user_id` | 37,082／37,082／15,845 | ID、用户名 | 未用 | 无 |
| `parent_entity` | 37,082 | 公司名 | 公司关联（不是付费赞助） | SponsorCandidate |
| `parent_entity_info.type`／`commodity`／`region` | 37,082 | 例：Investor-owned Company 22,773、State-owned Entity 7,531、Trade Association 6,778；USA 12,002、UK 6,928 | 未用 | 无 |
| `urls.post_url`／`junkipedia_link` | 37,082／37,048 | URL | 原帖链接、存档链接 | SourceArtifact |
| `post.is_reply` | 5,297 为 true | 其余 31,785 为 "Unknown" | 回复筛选（reply／not_marked） | 无 |
| `post.is_quote_or_retweet` | 915 为 true | 其余 36,167 为 "Unknown" | 未用 | 无 |
| `engagement.like_count`／`reply_count`／`retweet_count`／`view_count` | 各 37,082 | 整数，可为 0 | 未用 | 无 |
| `engagement.quote_count`／`bookmark_count` | 34,068／17,753 | 整数 | 未用 | 无 |
| `post.hashtags_identified` | 17,158 | 字符串列表；注意这是带点的顶层键名，不是嵌套在 `post` 下 | 未用 | 无 |
| `engagement.username_mentions` | 9,434 | 混合：字符串 4,200、列表 5,234 | 未用 | 无 |
| `engagement.referenced_tweet_ids` | 7,461 | 混合：字符串 7,443、列表 18 | 未用 | 无 |
| `post.reference_tweet_type` | 4,613 | replied_to 2,116、retweeted 2,056、quoted 441 | 未用 | 无 |
| `post.referenced_tweet_text` | 4,613 | 文本 | 未用，不进检索 | 无 |
| `engagement.replying_to_username`／`in_reply_to_user_id` | 3,491／1,784 | 用户名、ID | 未用 | 无 |
| `post.image_text`／`audio_text` | 1,440／33 | 文本 | 未用，不进检索 | 无 |
| `urls.media_url`／`post.content_type` | 10,886／21,688 | content_type 混合列表和字符串（photo、video、link、links） | 未用 | 无 |
| `post.link_description` | 1,162 | 文本 | 未用 | 无 |
| `geographic_info.user_location` | 27,923 | 账号自填位置 | 未用；不是发帖地点 | 无 |
| `language.detected` | 37,082 | 全部为 "en" | 未用；这里没有信息量 | 无 |
| `duplicate_info.*` | 3,843 行在重复组里 | — | 入库时另按 URL 合并重复 | 无 |
| `ads_data` | 0 | 全空 | — | 无；帖子不能认定为付费广告 |

## 四、未接入的字段

- **互动数**：点赞、回复、转发、浏览、引用、收藏数。
- **话题与提及**：`post.hashtags_identified`、`engagement.username_mentions`。
- **转发、引用、回复关系**：`referenced_tweet_ids`、`reference_tweet_type`、`replying_to_username`、`in_reply_to_user_id`、`is_quote_or_retweet`。
- **图片、音频、链接和被引用帖的文字**：`image_text`、`audio_text`、`link_description`、`referenced_tweet_text`、`media_url`、`content_type`。
- **账号与公司属性**：`channel_id`、`channel.username`、`channel.user_id`、`parent_entity_info.*`。
- **其他**：`created_at`、`modified_at`、`user_location`。

## 五、限制

- 没有 `conversation_id`，不能还原完整会话串，只有单条回复、引用、转发关系。
- `is_reply="Unknown"` 不等于“不是回复”。
- 提及和关联帖子 ID 混用字符串和列表，使用前要统一格式。
- 图片、音频文字是平台或采集方提取的，不是帖子正文，引用时要和正文分开标注。
- `ads_data` 全空：这些是公司账号的帖子，不是已确认的付费广告。

## 六、接入图谱（schema v4，2026-10-15）

`Database.knowledge_page` 从帖子被选中展示的那条原始行里，只取下列字段交给图谱；其他原始字段（如 `in_reply_to_user_id`、图片文字）不进入图谱输入。

| 原始字段 | 图谱 |
|---|---|
| `channel_id` | `Channel` 节点，边 `posted_from_channel` |
| `channel.username` | `Handle` 节点（不区分大小写），边 `channel_uses_handle` |
| `engagement.username_mentions` | 边 `mentions_handle` → `Handle`（字符串和列表统一、去重） |
| `engagement.replying_to_username` | 边 `replies_to_handle` → `Handle` |
| `post.hashtags_identified` | `Hashtag` 节点（不区分大小写；含空格的不算话题），边 `uses_hashtag` |
| `engagement.referenced_tweet_ids` + `post.reference_tweet_type` | `ReferencedPost` 节点；只有一个关联 ID 时才按类型连 `replies_to_post`／`quotes_post`／`reposts_post`，否则连 `references_post` |
| `parent_entity_info.*` | `AffiliationProfile` 节点，边 `source_profiles_affiliation`（从公司关联候选出发） |
| 点赞、回复、转发、引用、浏览、收藏数 | `SocialPost` 的 `engagement` 属性，注明是采集时一条来源行的读数，以及该帖的来源行数 |
| `urls.post_url` 里的帖子 ID | `SocialPost` 的 `platform_post_id` |

- 问答工具 `get_graph_neighborhood` 现在接受 social 和 all，不再强制改成 native。
- `ReferencedPost` 按原帖 URL 里的 status ID 对接库里已收录的帖子：对上时 `collection_status=collected_post` 并给出记录 ID 和详情链接，没对上时为 `not_in_collection`。全量 7,479 条引用中有 293 条对得上（回复 86、转发 89、引用 16、未标类型 102）。
- 检索仍只索引 `post_text`；图片、音频、被引用帖文字和链接说明仍未接入。
