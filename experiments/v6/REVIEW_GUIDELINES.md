# v6 ブラインドTEMレビュー手順

この監査は **候補粒子の測定可能性** を検証するもので、顕微鏡画像内の真の粒子全体の検出率ではない。再構成された元画像を使っているため、機器の元データによる粒径測定値として扱わない。

1. `audit_blind.csv`・正しい画像・`audit_manifest.json`のみをレビュー担当者へ渡す。`audit_private.csv`、モデルの採否、LoG優先度、過去の目視判定は表示しない。
2. 黄色い十字の中心と拡大図および全視野の両方を見て、粒子候補を1つずつ判断する。拡大表示にない周辺の粒子も確認する。
3. **single**：測れる単粒子の独立した輪郭。球形とは限らない。**touching_separable**：隣接・接触しているが対象粒子の境界を合理的に分離できる。**overlap**：重なりで投影輪郭が復元できない、あるいは不可分な凝集。**background**：支持膜・ノイズ・文字等。**uncertain**：画質や境界から決められない。
4. **2名が独立して記録**。同じカテゴリなら暫定合意。違う場合は別担当の仲裁判定を記録する。仲裁がない候補は不一致として残す。
5. 目視で測れそうな候補のみ任意の直径pxを記録する。画素数の精度が不十分なら空欄。**5 nmの公称粒径を正解として使用しない**。
6. レビューCSVは追記専用。署名はアカウント認証ではなく自己申告の識別子なので、機関研究用ではレビュー担当者の記録・監督が別途必要。
7. 評価は全6層の選択サンプルが分類確定してから行う。`uncertain` が残れば最終的な外挿は止める。層別抽出の重みは母数と抽出率で計算し、救済候補の割合を単純平均しない。
8. 確定済み候補から新たな**物体レベルの学習例**を作成可能。ただしピクセル単位の正解マスクではなく、同じ視野の画像を学習と独立評価に分割しない。

## コマンド

```bash
# モデルの出力CSVと同じ画像から準備
python v6/audit_protocol.py prepare --image path/to/pt.png \
  --candidates results/pt/review_triage_all.csv --out results/pt/audit \
  --per-stratum 10 --exclude-ids-csv v5/spotcheck_candidates.csv
python v6/audit_protocol.py gallery --image path/to/pt.png \
  --blind results/pt/audit/audit_blind.csv \
  --manifest results/pt/audit/audit_manifest.json \
  --out results/pt/audit/blind_gallery.jpg

# 画像・モデルの状態がレビュー担当者に見えないGUI
python v6/app_double_review.py

# 少なくとも2名の判定後に候補レビューを集計
python v6/audit_protocol.py evaluate \
  --manifest results/pt/audit/audit_manifest.json \
  --private results/pt/audit/audit_private.csv \
  --events results/pt/audit/review_events.jsonl \
  --out results/pt/audit/evaluation
```

`audit_private.csv`はコーディネーターが保持。今回はブラインド性を維持するためGitHubにはアップロードしない。
