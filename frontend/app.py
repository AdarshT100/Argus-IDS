import os
import requests
import streamlit as st

def get_backend_url():
    return st.sidebar.text_input("Backend URL", value=os.getenv("ARGUS_BACKEND_URL", "http://localhost:8000"))

def health_check(backend_url: str):
    st.subheader("Backend Health")
    try:
        resp = requests.get(f"{backend_url.rstrip('/')}/health", timeout=5)
        if resp.ok:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            st.success(f"Healthy — {data}")
        else:
            st.error(f"Unhealthy — {resp.status_code} {resp.text}")
    except Exception as e:
        st.error(f"Error contacting backend: {e}")

def overview_page(backend_url: str):
    st.title("Argus IDS — Overview / Dashboard")
    health_check(backend_url)
    st.markdown("""\
This is the initial Overview page. Charts and aggregates will be added iteratively.
""")

def placeholder_page(name: str):
    def _page(backend_url: str):
        st.title(name)
        st.info("Not implemented yet. Will be added in subsequent steps.")
    return _page


def _find_value_recursive(data, keys):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and value is not None:
                return value
            found = _find_value_recursive(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_value_recursive(item, keys)
            if found is not None:
                return found
    return None


def render_shap_and_explanation(result: dict):
    shap_items = _find_value_recursive(result, ("shap_top_features", "top_features", "shap", "shap_values", "shap_values_top"))
    explanation = _find_value_recursive(result, ("explanation_text", "explanation", "human_explanation", "reason", "why"))

    if isinstance(shap_items, dict):
        shap_data = shap_items
    elif isinstance(shap_items, list):
        shap_data = shap_items
    else:
        shap_data = None

    if shap_data:
        try:
            import pandas as pd
            import plotly.express as px

            if isinstance(shap_data, dict):
                df = pd.DataFrame(list(shap_data.items()), columns=["feature", "shap_value"])
            else:
                df = pd.DataFrame(shap_data)

            feature_col = None
            shap_col = None
            cols = list(df.columns)
            if "feature" in cols:
                feature_col = "feature"
            elif "name" in cols:
                feature_col = "name"
            elif len(cols) >= 1 and df[cols[0]].dtype == object:
                feature_col = cols[0]
            if feature_col is None and len(cols) >= 1:
                feature_col = cols[0]

            for c in cols:
                if c == feature_col:
                    continue
                if pd.api.types.is_numeric_dtype(df[c]):
                    shap_col = c
                    break
            if shap_col is None and len(cols) >= 2:
                for c in cols:
                    if c != feature_col:
                        shap_col = c
                        break

            if shap_col is None:
                st.write("SHAP data present but no numeric SHAP column found.")
            else:
                plot_df = df[[feature_col, shap_col]].rename(columns={feature_col: "feature", shap_col: "shap_value"})
                plot_df["shap_value"] = pd.to_numeric(plot_df["shap_value"], errors="coerce").fillna(0.0)
                plot_df = plot_df.assign(abs_shap=plot_df["shap_value"].abs()).sort_values("abs_shap", ascending=False).head(20)
                st.subheader("SHAP — top features")
                fig = px.bar(plot_df, x="shap_value", y="feature", orientation='h', color="shap_value", color_continuous_scale='RdBu')
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.write("SHAP data present but failed to render chart:", e)

    if not explanation:
        prediction = result.get("prediction") or result.get("label")
        severity = result.get("severity")
        if prediction or severity:
            explanation_parts = []
            if prediction and severity:
                explanation_parts.append(f"Predicted **{prediction}** with severity **{severity}**.")
            elif prediction:
                explanation_parts.append(f"Predicted **{prediction}**.")
            elif severity:
                explanation_parts.append(f"Severity: **{severity}**.")

            if isinstance(shap_items, list):
                top_names = []
                for item in shap_items[:4]:
                    if isinstance(item, dict) and "feature" in item:
                        top_names.append(item.get("feature"))
                    elif isinstance(item, dict) and "name" in item:
                        top_names.append(item.get("name"))
                if top_names:
                    explanation_parts.append("Top contributing features: " + ", ".join(top_names) + ".")
            elif isinstance(shap_items, dict):
                top_names = list(shap_items.keys())[:4]
                if top_names:
                    explanation_parts.append("Top contributing features: " + ", ".join(top_names) + ".")

            explanation = " ".join(explanation_parts)

    if explanation:
        st.markdown("### Why this decision?")
        st.info(explanation)

def main():
    st.set_page_config(page_title="Argus IDS UI", layout="wide")
    backend_url = get_backend_url()

    def real_time_prediction_page(backend_url: str):
        st.title("Real-time Prediction")
        st.markdown("Enter a single-packet JSON payload or use a random sample from the server.")

        payload_text = st.text_area("Single-packet JSON", height=250, placeholder='{"feature1": val, "feature2": val, ... }')
        btn_col1, btn_col2 = st.columns([1, 1])
        with btn_col1:
            predict_btn = st.button("Predict")
        with btn_col2:
            random_btn = st.button("Random sample from server")

        if "last_prediction_result" not in st.session_state:
            st.session_state.last_prediction_result = None

        if random_btn:
            try:
                resp = requests.post(f"{backend_url.rstrip('/')}/predict/random", timeout=10)
                if resp.ok:
                    st.session_state.last_prediction_result = resp.json()
                    st.success("Random prediction received")
                else:
                    st.error(f"Random predict failed: {resp.status_code} {resp.text}")
            except Exception as e:
                st.error(f"Error calling backend: {e}")

        if predict_btn:
            if not payload_text.strip():
                st.warning("Please provide a single-packet JSON payload or use the random sample button.")
            else:
                try:
                    import json
                    payload = json.loads(payload_text)
                    resp = requests.post(f"{backend_url.rstrip('/')}/predict", json=payload, timeout=10)
                    if resp.ok:
                        st.session_state.last_prediction_result = resp.json()
                        st.success("Prediction returned")
                    else:
                        st.error(f"Predict failed: {resp.status_code} {resp.text}")
                except Exception as e:
                    st.error(f"Invalid JSON or backend error: {e}")

        result_container = st.container()
        if st.session_state.last_prediction_result is not None:
            with result_container:
                st.subheader("Prediction output")
                st.json(st.session_state.last_prediction_result)
                render_shap_and_explanation(st.session_state.last_prediction_result)

    def render_simulation_results(sim_result: dict):
        import pandas as pd
        import plotly.express as px

        # Try common keys
        windows = None
        if isinstance(sim_result, dict):
            for key in ("windows", "results", "simulation_windows", "window_scores"):
                if key in sim_result:
                    windows = sim_result.get(key)
                    break
        if windows is None and isinstance(sim_result, list):
            windows = sim_result

        if windows:
            try:
                # windows expected as list of {timestamp, score, anomaly_count} or similar
                df = pd.DataFrame(windows)
                # find timestamp-like and score-like columns
                time_col = None
                score_col = None
                for c in df.columns:
                    if c.lower() in ("timestamp", "time", "ts"):
                        time_col = c
                    if c.lower() in ("score", "anomaly_score", "anomaly_rate", "risk", "avg_score"):
                        score_col = c
                if time_col is None and "start_time" in df.columns:
                    time_col = "start_time"
                if score_col is None:
                    # pick first numeric column not time_col
                    for c in df.columns:
                        if c == time_col:
                            continue
                        if pd.api.types.is_numeric_dtype(df[c]):
                            score_col = c
                            break

                if time_col:
                    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
                    df = df.sort_values(time_col)

                st.subheader("Simulation windows")
                st.write(df.head(10))

                if time_col and score_col:
                    fig = px.line(df, x=time_col, y=score_col, title="Window anomaly score over time")
                    st.plotly_chart(fig, use_container_width=True)
                elif score_col:
                    fig = px.line(df, y=score_col, title="Window anomaly score (index)")
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.write("Failed to render simulation results:", e)
        else:
            st.write("No windowed results found in simulation response.")

    def simulation_page(backend_url: str):
        st.title("Simulation / Window Analysis")
        st.markdown("Run a sliding-window simulation over server-side data and inspect past runs.")

        with st.expander("Run new simulation"):
            cols = st.columns(3)
            window_size = cols[0].number_input("Window size", min_value=1, max_value=10000, value=100, step=1)
            stride = cols[1].number_input("Stride", min_value=1, max_value=10000, value=10, step=1)
            max_windows = cols[2].number_input("Max windows (0 = all)", min_value=0, max_value=100000, value=0, step=1)
            run = st.button("Run simulation")

            if run:
                payload = {"window_size": int(window_size), "stride": int(stride)}
                if int(max_windows) > 0:
                    payload["max_windows"] = int(max_windows)
                try:
                    with st.spinner("Running simulation on server..."):
                        resp = requests.post(f"{backend_url.rstrip('/')}/simulate", json=payload, timeout=120)
                    if resp.ok:
                        result = resp.json()
                        st.success("Simulation completed / queued")
                        st.json(result)
                        render_simulation_results(result)
                    else:
                        st.error(f"Simulation failed: {resp.status_code} {resp.text}")
                except Exception as e:
                    st.error(f"Error calling simulate endpoint: {e}")

        st.markdown("---")
        st.subheader("Past simulations")

        if "simulations" not in st.session_state:
            st.session_state.simulations = None

        if st.button("Refresh simulations list"):
            try:
                resp = requests.get(f"{backend_url.rstrip('/')}/simulations", timeout=10)
                if resp.ok:
                    st.session_state.simulations = resp.json()
                else:
                    st.error(f"Failed to list simulations: {resp.status_code} {resp.text}")
            except Exception as e:
                st.error(f"Error contacting backend for simulations: {e}")

        if st.session_state.simulations is not None:
            import pandas as pd
            df = pd.DataFrame(st.session_state.simulations)
            st.write(df)
            sid = st.selectbox("Select simulation to inspect", options=[None] + list(df.index.astype(str)))
            if sid:
                try:
                    if "id" in df.columns:
                        sim_id = df.loc[int(sid), "id"]
                    else:
                        sim_id = sid
                    dresp = requests.get(f"{backend_url.rstrip('/')}/simulations/{sim_id}", timeout=10)
                    if dresp.ok:
                        detail = dresp.json()
                        st.json(detail)
                        render_simulation_results(detail)
                    else:
                        st.info("No per-simulation detail endpoint; showing row data")
                        st.json(df.loc[int(sid)].to_dict())
                except Exception as e:
                    st.write("Failed to fetch simulation detail:", e)

    def alerts_page(backend_url: str):
        st.title("Alerts / Log")
        st.markdown("View network alerts detected by the model and refresh manually.")

        if "alerts" not in st.session_state:
            st.session_state.alerts = None

        if st.button("Refresh alerts"):
            try:
                resp = requests.get(f"{backend_url.rstrip('/')}/alerts", timeout=10)
                if resp.ok:
                    data = resp.json()
                    st.session_state.alerts = data.get("alerts", []) if isinstance(data, dict) else data
                    st.session_state.alert_total = data.get("total", len(st.session_state.alerts)) if isinstance(data, dict) else len(st.session_state.alerts)
                    st.success("Alerts refreshed")
                else:
                    st.error(f"Failed to load alerts: {resp.status_code} {resp.text}")
            except Exception as e:
                st.error(f"Error fetching alerts: {e}")

        if st.session_state.alerts is None:
            st.info("No alerts loaded yet. Click refresh to fetch alerts from the backend.")
            return

        try:
            import pandas as pd

            alerts_df = pd.json_normalize(st.session_state.alerts)
            if "timestamp" in alerts_df.columns:
                alerts_df["timestamp"] = pd.to_datetime(alerts_df["timestamp"], errors="coerce")
                if alerts_df["timestamp"].dt.tz is not None:
                    alerts_df["timestamp"] = alerts_df["timestamp"].dt.tz_convert(None)

            prediction_col = next((c for c in alerts_df.columns if "pred" in c.lower() or c.lower() == "label"), None)
            severity_col = next((c for c in alerts_df.columns if "severity" in c.lower()), None)

            with st.expander("Filter alerts", expanded=True):
                filter_cols = st.columns([2, 2, 3])
                with filter_cols[0]:
                    if prediction_col:
                        pred_values = sorted(alerts_df[prediction_col].dropna().astype(str).unique())
                    else:
                        pred_values = []
                    selected_predictions = st.multiselect(
                        "Prediction",
                        pred_values,
                        default=st.session_state.get("alert_pred_filter", pred_values),
                        key="alert_pred_filter",
                    )
                with filter_cols[1]:
                    if severity_col:
                        sev_values = sorted(alerts_df[severity_col].dropna().astype(str).unique())
                    else:
                        sev_values = []
                    selected_severity = st.multiselect(
                        "Severity",
                        sev_values,
                        default=st.session_state.get("alert_sev_filter", sev_values),
                        key="alert_sev_filter",
                    )
                with filter_cols[2]:
                    if "timestamp" in alerts_df.columns and not alerts_df["timestamp"].isna().all():
                        min_date = alerts_df["timestamp"].min().date()
                        max_date = alerts_df["timestamp"].max().date()
                        default_range = st.session_state.get("alert_date_range", (min_date, max_date))
                        date_range = st.date_input(
                            "Date range",
                            value=default_range,
                            min_value=min_date,
                            max_value=max_date,
                            key="alert_date_range",
                        )
                    else:
                        date_range = None

            filtered_df = alerts_df.copy()
            if prediction_col and selected_predictions is not None and selected_predictions:
                filtered_df = filtered_df[filtered_df[prediction_col].astype(str).isin(selected_predictions)]
            if severity_col and selected_severity is not None and selected_severity:
                filtered_df = filtered_df[filtered_df[severity_col].astype(str).isin(selected_severity)]
            if date_range and len(date_range) == 2 and "timestamp" in filtered_df.columns:
                start_dt = pd.to_datetime(date_range[0])
                end_dt = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                filtered_df = filtered_df[(filtered_df["timestamp"] >= start_dt) & (filtered_df["timestamp"] <= end_dt)]

            st.markdown("---")
            st.write(f"Showing **{len(filtered_df)}** alert rows.")
            if not filtered_df.empty:
                st.dataframe(filtered_df)
                csv = filtered_df.to_csv(index=False).encode("utf-8")
                st.download_button("Download filtered alerts as CSV", csv, file_name="alerts.csv", mime="text/csv")
            else:
                st.warning("No alerts match the selected filters.")
        except Exception as e:
            st.error(f"Failed to render alerts: {e}")

    def model_evaluation_page(backend_url: str):
        st.title("Model & Evaluation")
        st.markdown("View available evaluation summaries derived from backend simulation and alert logs.")
        st.info("Full confusion matrix, ROC/PR curves, and calibration data are not currently exposed by the API. This page shows best-effort charts from available endpoints.")

        sim_data = None
        alert_data = None
        try:
            resp = requests.get(f"{backend_url.rstrip('/')}/simulations", timeout=10)
            if resp.ok:
                sim_json = resp.json()
                sim_data = sim_json.get("simulations", sim_json) if isinstance(sim_json, dict) else sim_json
        except Exception:
            st.warning("Could not fetch simulations data.")

        try:
            resp = requests.get(f"{backend_url.rstrip('/')}/alerts", timeout=10)
            if resp.ok:
                alerts_json = resp.json()
                alert_data = alerts_json.get("alerts", alerts_json) if isinstance(alerts_json, dict) else alerts_json
        except Exception:
            st.warning("Could not fetch alerts data.")

        if sim_data is None and alert_data is None:
            st.error("No evaluation data available from the backend.")
            return

        import pandas as pd
        import plotly.express as px

        if sim_data is not None:
            sim_df = pd.json_normalize(sim_data)
            if sim_df.empty:
                st.warning("Simulation endpoint returned no records.")
            else:
                st.subheader("Simulation summary")
                st.metric("Simulation runs", len(sim_df))
                if "severity" in sim_df.columns:
                    severity_counts = sim_df["severity"].value_counts().reset_index()
                    severity_counts.columns = ["severity", "count"]
                    fig = px.bar(severity_counts, x="severity", y="count", color="severity", title="Simulation severity distribution")
                    st.plotly_chart(fig, use_container_width=True)
                if "attack_count" in sim_df.columns:
                    fig = px.histogram(sim_df, x="attack_count", nbins=10, title="Attack count distribution")
                    st.plotly_chart(fig, use_container_width=True)
                if "mean_risk_score" in sim_df.columns:
                    fig = px.line(sim_df, y="mean_risk_score", title="Mean risk score over recent simulation runs")
                    st.plotly_chart(fig, use_container_width=True)

        if alert_data is not None:
            alerts_df = pd.json_normalize(alert_data)
            if alerts_df.empty:
                st.warning("Alert endpoint returned no records.")
            else:
                st.subheader("Alert log summary")
                st.metric("Alert records", len(alerts_df))
                if "severity" in alerts_df.columns:
                    severity_counts = alerts_df["severity"].value_counts().reset_index()
                    severity_counts.columns = ["severity", "count"]
                    fig = px.pie(severity_counts, values="count", names="severity", title="Alert severity mix")
                    st.plotly_chart(fig, use_container_width=True)
                pred_col = next((c for c in alerts_df.columns if "pred" in c.lower() or c.lower() == "label"), None)
                if pred_col is not None:
                    pred_counts = alerts_df[pred_col].value_counts().reset_index()
                    pred_counts.columns = ["prediction", "count"]
                    fig = px.bar(pred_counts, x="prediction", y="count", title="Prediction distribution in alert log")
                    st.plotly_chart(fig, use_container_width=True)
                if "confidence" in alerts_df.columns:
                    fig = px.histogram(alerts_df, x="confidence", nbins=10, title="Confidence distribution")
                    st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("**Note:** To support full model benchmarking, the backend should expose an evaluation endpoint with confusion matrix, ROC/PR, and calibration curve data.")

    pages = {
        "Overview": overview_page,
        "Real-time Prediction": real_time_prediction_page,
        "Simulation": simulation_page,
        "Alerts": alerts_page,
        "Model & Evaluation": model_evaluation_page,
    }

    page = st.sidebar.radio("Pages", list(pages.keys()))
    pages[page](backend_url)

if __name__ == "__main__":
    main()
