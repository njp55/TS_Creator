import streamlit as st
import pandas as pd
import io
import zipfile
import xml.etree.ElementTree as ET
import re
from datetime import datetime

# ==========================================
# ページ設定と初期化
# ==========================================
st.set_page_config(page_title="XPT/XML Generator", layout="wide")

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "meta_df" not in st.session_state:
    st.session_state.meta_df = pd.DataFrame()
if "dataset_name" not in st.session_state:
    st.session_state.dataset_name = "DM"
if "dataset_label" not in st.session_state:
    st.session_state.dataset_label = "Demographics"

# ==========================================
# サイドバー (UI・システム機能)
# ==========================================
st.sidebar.header("設定・ステータス")
xpt_version = st.sidebar.selectbox("XPTバージョン", ["V5", "V8"]) # [cite: 79]

if st.sidebar.button("すべてクリア (Reset)", type="primary"): # [cite: 80]
    st.session_state.df = pd.DataFrame()
    st.session_state.meta_df = pd.DataFrame()
    st.rerun()

st.sidebar.subheader("ステータスダッシュボード") # [cite: 81]
st.sidebar.write(f"総行数: {len(st.session_state.df)}")
st.sidebar.write(f"列数(変数数): {len(st.session_state.df.columns) if not st.session_state.df.empty else 0}")

# ==========================================
# メインパネル (タブ構成)
# ==========================================
st.title("XPT・XML自動生成アプリケーション")
tab1, tab2, tab3 = st.tabs(["Step 1: データ入力", "Step 2: メタデータ定義", "Step 3: 検証と出力"]) # [cite: 83, 84, 88, 92]

# ------------------------------------------
# Tab 1: データ入力 (Data Input & Preview)
# ------------------------------------------
with tab1:
    st.header("データセット情報とデータ入力")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.dataset_name = st.text_input("データセット名 (例: DM)", value=st.session_state.dataset_name) # [cite: 43]
    with col2:
        st.session_state.dataset_label = st.text_input("データセットラベル", value=st.session_state.dataset_label) # [cite: 43]

    uploaded_file = st.file_uploader("CSV または Excelファイルをアップロード", type=["csv", "xlsx"]) # [cite: 40]
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            st.session_state.df = df
            st.success("ファイルを読み込みました。")
        except Exception as e:
            st.error(f"ファイルの読み込みに失敗しました: {e}")

    st.subheader("データエディタ (マニュアル入力・編集)")
    # [cite: 36, 38] st.data_editorによる直接編集・行追加
    st.session_state.df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True)

# ------------------------------------------
# Tab 2: メタデータ定義 (Metadata Configuration)
# ------------------------------------------
with tab2:
    st.header("メタデータ定義")
    if not st.session_state.df.empty:
        # メタデータの自動推論 (Auto-detect) 
        if st.session_state.meta_df.empty or len(st.session_state.meta_df) != len(st.session_state.df.columns):
            meta_records = []
            for col in st.session_state.df.columns:
                dtype = "Numeric" if pd.api.types.is_numeric_dtype(st.session_state.df[col]) else "Character"
                length = 8 if dtype == "Numeric" else 200
                meta_records.append({
                    "Original Column": col,
                    "Variable Name": str(col)[:8].upper(), # [cite: 52] 8文字以内
                    "Variable Label": str(col)[:40], # [cite: 53] 40バイト以内
                    "Type": dtype,
                    "Length": length
                })
            st.session_state.meta_df = pd.DataFrame(meta_records)

        st.info("※XPT V5では変数名は8文字以内、半角英数字とアンダースコアのみに制限されています。") # [cite: 105]
        # [cite: 44, 45, 46, 47, 48, 90] 変数名、ラベル、型、長さのグリッド入力
        st.session_state.meta_df = st.data_editor(
            st.session_state.meta_df,
            column_config={
                "Type": st.column_config.SelectboxColumn("Type", options=["Character", "Numeric"], required=True),
                "Length": st.column_config.NumberColumn("Length", min_value=1, max_value=200, required=True)
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("先にTab 1でデータを入力・アップロードしてください。")

# ------------------------------------------
# Tab 3: 検証と出力 (Validate & Export)
# ------------------------------------------
with tab3:
    st.header("検証とファイル出力")
    
    if st.button("✅ バリデーションを実行", type="primary"): # [cite: 93]
        errors = []
        df = st.session_state.df
        meta_df = st.session_state.meta_df
        ds_name = st.session_state.dataset_name

        # 必須項目チェック [cite: 57, 58]
        if not ds_name:
            errors.append("データセット名が入力されていません。")
        if meta_df.empty:
            errors.append("メタデータが設定されていません。")

        # 変数名・ラベル長・型の検証 [cite: 51]
        for idx, row in meta_df.iterrows():
            var_name = str(row.get("Variable Name", ""))
            var_label = str(row.get("Variable Label", ""))
            var_type = row.get("Type", "")
            orig_col = row.get("Original Column", "")

            # [cite: 52] 変数名ルール: 8文字以内, 英数字/_のみ, 先頭英字
            if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,7}$", var_name):
                errors.append(f"変数名エラー ({orig_col}): '{var_name}' は無効です。8文字以内の英数字・アンダースコアとし、先頭は英字にしてください。")
            
            # [cite: 53] 変数ラベルルール: 40バイト以内
            if len(var_label.encode('utf-8')) > 40:
                errors.append(f"変数ラベルエラー ({orig_col}): ラベルは40バイト以内にしてください。")

            # [cite: 55, 56] 型と不整合の検知
            if var_type == "Numeric" and orig_col in df.columns:
                non_numeric = pd.to_numeric(df[orig_col], errors='coerce').isna() & df[orig_col].notna()
                if non_numeric.any():
                    bad_indices = df[non_numeric].index.tolist()
                    errors.append(f"データ型エラー ({orig_col}): 数値型として設定されていますが、変換不可能な文字列が含まれています (行インデックス: {bad_indices})。")

        if errors:
            st.error("以下のバリデーションエラーを修正してください。") # [cite: 59, 60]
            for e in errors:
                st.write(f"- {e}")
        else:
            st.success("バリデーションに成功しました！ファイルの生成を行います。") # [cite: 94]
            
            # ==============================
            # XPT生成 (モック/メモリ上) [cite: 62]
            # ==============================
            xpt_buffer = io.BytesIO()
            try:
                # 実際の運用では import xport; xport.v56.dump(df, xpt_buffer) 等を使用
                df.to_csv(xpt_buffer, index=False) # ※環境依存を避けるための仮処理。実態に合わせてxportライブラリに置換。
                xpt_data = xpt_buffer.getvalue()
            except Exception as e:
                st.error(f"XPT生成エラー: {e}")
                xpt_data = b""

            # ==============================
            # XML生成 (Define-XML構造) [cite: 64, 65, 66]
            # ==============================
            odm = ET.Element("ODM", CreationDateTime=datetime.now().isoformat())
            study = ET.SubElement(odm, "Study", OID="STUDY01")
            meta_data_version = ET.SubElement(study, "MetaDataVersion", OID="MDV01", Name="Define-XML")
            
            # ItemGroupDef [cite: 67]
            item_group_def = ET.SubElement(meta_data_version, "ItemGroupDef", OID=f"IG.{ds_name}", Name=ds_name, Label=st.session_state.dataset_label)
            
            for _, row in meta_df.iterrows():
                var_name = row["Variable Name"]
                # ItemRef [cite: 69]
                ET.SubElement(item_group_def, "ItemRef", ItemOID=f"IT.{ds_name}.{var_name}", Mandatory="Yes")
                # ItemDef [cite: 68]
                ET.SubElement(meta_data_version, "ItemDef", OID=f"IT.{ds_name}.{var_name}", Name=var_name, DataType=row["Type"], Length=str(row["Length"]))

            xml_str = ET.tostring(odm, encoding="utf-8", xml_declaration=True).decode("utf-8")
            
            # ==============================
            # ダウンロードUI [cite: 71]
            # ==============================
            st.subheader("出力ファイル")
            col_xpt, col_xml, col_zip = st.columns(3)
            
            xpt_filename = f"{ds_name.lower()}.xpt" # [cite: 73] 動的ファイル名付与
            xml_filename = f"{ds_name.lower()}_define.xml"
            
            with col_xpt:
                st.download_button("💾 XPTダウンロード", data=xpt_data, file_name=xpt_filename, mime="application/octet-stream") # [cite: 72]
            with col_xml:
                st.download_button("💾 XMLダウンロード", data=xml_str, file_name=xml_filename, mime="application/xml")
            
            # ZIP一括ダウンロード [cite: 74]
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(xpt_filename, xpt_data)
                zf.writestr(xml_filename, xml_str)
            
            with col_zip:
                st.download_button("📦 ZIP一括ダウンロード", data=zip_buffer.getvalue(), file_name=f"{ds_name.lower()}_export.zip", mime="application/zip")

            with st.expander("XMLプレビューを表示"): # [cite: 95]
                st.code(xml_str, language="xml")