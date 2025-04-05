from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import os
import json
import httpx
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.io as pio
from io import BytesIO
from fpdf import FPDF
from dotenv import load_dotenv
import uuid
from pathlib import Path
import tempfile
import asyncio
from typing import List, Optional

# Load environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set")

app = FastAPI(title="AI Data Analysis Workspace")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create temp directories for uploads and outputs
UPLOAD_DIR = Path("temp/uploads")
OUTPUT_DIR = Path("temp/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global data store - in production use a proper database
data_store = {}

@app.get("/", response_class=HTMLResponse)
async def get_html():
    return FileResponse("static/index.html")

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and process CSV or Excel files"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_extension = file.filename.split(".")[-1].lower()
    if file_extension not in ["csv", "xlsx", "xls"]:
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
    
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.{file_extension}"
    
    # Save the file
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Read the data
    try:
        if file_extension == "csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # Store the data
        data_store[file_id] = {
            "filename": file.filename,
            "path": str(file_path),
            "columns": df.columns.tolist(),
            "df": df
        }
        
        return {"file_id": file_id, "filename": file.filename, "columns": df.columns.tolist(), 
                "preview": df.head(5).to_dict(orient="records")}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/api/analyze")
async def analyze_data(file_id: str = Form(...), query: str = Form(...)):
    """Analyze data using Llama 3.3 via OpenRouter"""
    if file_id not in data_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    data = data_store[file_id]
    df = data["df"]
    
    # Prepare data summary for the AI
    data_summary = {
        "columns": df.columns.tolist(),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "shape": df.shape,
        "sample": df.head(5).to_dict(orient="records")
    }
    
    # Create prompt for AI
    prompt = f"""
You are a data analysis assistant. Analyze the following dataset based on this query: "{query}"

Dataset Summary:
Columns: {data_summary['columns']}
Data Types: {data_summary['dtypes']}
Shape: {data_summary['shape']}
Sample Data: {data_summary['sample']}

Please provide:
1. A clear analysis responding to the query
2. Suggested visualizations (if applicable)
3. Python code to create those visualizations using matplotlib or plotly
4. Any insights from the data

Format your response as JSON with these keys: 
"analysis", "visualization_code", "insights"
"""
    
    # Call OpenRouter API to access Llama 3.3
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000"  # Update in production
                },
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct",  # Using Llama 3.3 70B model
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extract the analysis from the AI response
            ai_analysis = json.loads(result["choices"][0]["message"]["content"])
            
            # If visualization code exists, try to execute it
            visualization_path = None
            if "visualization_code" in ai_analysis and ai_analysis["visualization_code"]:
                try:
                    # Create a namespace with required libraries
                    viz_namespace = {
                        "pd": pd, 
                        "plt": plt,
                        "px": px,
                        "df": df,
                        "BytesIO": BytesIO,
                    }
                    
                    # Try to execute the visualization code
                    exec(ai_analysis["visualization_code"], viz_namespace)
                    
                    # If matplotlib was used
                    if "plt" in ai_analysis["visualization_code"]:
                        vis_id = str(uuid.uuid4())
                        visualization_path = f"/temp/outputs/{vis_id}.png"
                        plt.savefig(f"{OUTPUT_DIR}/{vis_id}.png")
                        plt.close()
                    
                    # If plotly was used
                    elif "px" in ai_analysis["visualization_code"]:
                        if "fig" in viz_namespace:
                            vis_id = str(uuid.uuid4())
                            visualization_path = f"/temp/outputs/{vis_id}.png"
                            viz_namespace["fig"].write_image(f"{OUTPUT_DIR}/{vis_id}.png")
                except Exception as e:
                    ai_analysis["visualization_error"] = str(e)
            
            return {
                "analysis": ai_analysis.get("analysis", "No analysis provided"),
                "insights": ai_analysis.get("insights", "No insights provided"),
                "visualization": visualization_path
            }
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, 
                               detail=f"Error from OpenRouter API: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error analyzing data: {str(e)}")

@app.post("/api/visualize")
async def create_visualization(
    file_id: str = Form(...),
    viz_type: str = Form(...),
    x_column: str = Form(...),
    y_column: Optional[str] = Form(None),
    color_by: Optional[str] = Form(None)
):
    """Create visualization based on specified parameters"""
    if file_id not in data_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    data = data_store[file_id]
    df = data["df"]
    
    if x_column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column {x_column} not found in data")
    
    if y_column and y_column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column {y_column} not found in data")
    
    if color_by and color_by not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column {color_by} not found in data")
    
    try:
        vis_id = str(uuid.uuid4())
        output_path = OUTPUT_DIR / f"{vis_id}.png"
        
        # Create different visualizations based on type
        if viz_type == "bar":
            if not y_column:
                fig = px.bar(df, x=x_column, color=color_by)
            else:
                fig = px.bar(df, x=x_column, y=y_column, color=color_by)
        
        elif viz_type == "line":
            if not y_column:
                raise HTTPException(status_code=400, detail="Y column required for line chart")
            fig = px.line(df, x=x_column, y=y_column, color=color_by)
        
        elif viz_type == "scatter":
            if not y_column:
                raise HTTPException(status_code=400, detail="Y column required for scatter plot")
            fig = px.scatter(df, x=x_column, y=y_column, color=color_by)
        
        elif viz_type == "histogram":
            fig = px.histogram(df, x=x_column, color=color_by)
            
        elif viz_type == "box":
            if not y_column:
                fig = px.box(df, x=x_column, color=color_by)
            else:
                fig = px.box(df, x=x_column, y=y_column, color=color_by)
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported visualization type: {viz_type}")
        
        # Save the visualization
        fig.write_image(str(output_path))
        
        return {"visualization": f"/temp/outputs/{vis_id}.png"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating visualization: {str(e)}")

@app.post("/api/generate-report")
async def generate_report(
    file_id: str = Form(...),
    analysis_text: str = Form(...),
    visualization_paths: List[str] = Form([])
):
    """Generate a PDF report with analysis and visualizations"""
    if file_id not in data_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        
        # Add title
        pdf.cell(0, 10, f"Data Analysis Report: {data_store[file_id]['filename']}", ln=True)
        pdf.ln(10)
        
        # Add analysis
        pdf.set_font("Arial", "", 12)
        pdf.multi_cell(0, 10, "Analysis:")
        pdf.set_font("Arial", "", 10)
        
        # Split analysis into paragraphs
        for paragraph in analysis_text.split('\n'):
            if paragraph.strip():
                pdf.multi_cell(0, 10, paragraph)
        
        # Add visualizations
        if visualization_paths:
            pdf.ln(5)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, "Visualizations:", ln=True)
            
            for i, viz_path in enumerate(visualization_paths):
                try:
                    # Remove the leading slash if present
                    if viz_path.startswith("/"):
                        viz_path = viz_path[1:]
                    
                    img_path = Path(viz_path)
                    if not img_path.exists():
                        continue
                    
                    pdf.ln(5)
                    pdf.cell(0, 10, f"Visualization {i+1}", ln=True)
                    pdf.image(str(img_path), x=10, w=180)
                    pdf.ln(5)
                except Exception as e:
                    pdf.multi_cell(0, 10, f"Error adding visualization: {str(e)}")
        
        # Save PDF
        report_id = str(uuid.uuid4())
        report_path = OUTPUT_DIR / f"{report_id}.pdf"
        pdf.output(str(report_path))
        
        return {"report": f"/temp/outputs/{report_id}.pdf"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

@app.post("/api/auto-analyze")
async def auto_analyze_data(file_id: str = Form(...)):
    """Automatically analyze data and create visualization dashboard"""
    if file_id not in data_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    data = data_store[file_id]
    df = data["df"]
    
    # Prepare data summary for the AI
    data_summary = {
        "columns": df.columns.tolist(),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "shape": df.shape,
        "sample": df.head(5).to_dict(orient="records"),
        "numeric_summaries": df.describe().to_dict() if any(df.select_dtypes(include=['number']).columns) else {},
        "missing_values": df.isna().sum().to_dict()
    }
    
    # Create prompt for automated EDA
    prompt = f"""
You are an automated data analysis assistant. Perform exploratory data analysis on the dataset and create a comprehensive dashboard.

Dataset Summary:
Columns: {data_summary['columns']}
Data Types: {data_summary['dtypes']}
Shape: {data_summary['shape']}
Sample Data: {data_summary['sample']}
Numeric Summaries: {data_summary['numeric_summaries']}
Missing Values: {data_summary['missing_values']}

Please provide:
1. Initial data quality assessment (missing values, outliers, data types)
2. Preprocessing recommendations (handling missing values, encoding, normalization needs)
3. Key statistics and distributions for important variables
4. Correlation analysis between variables
5. Interesting patterns, trends or anomalies
6. Top 5 most insightful visualizations with Python code (use matplotlib or plotly)
7. A summary of key insights from the data

Return your response as JSON with these keys:
"data_quality": assessment of data quality issues,
"preprocessing": recommended preprocessing steps,
"statistics": key statistical findings,
"correlations": correlation analysis results,
"patterns": identified patterns or trends,
"visualizations": array of visualization objects with "title", "description" and "code",
"insights": key takeaways from the analysis
"""
    
    # Call OpenRouter API to access Llama 3.3
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000"  # Update in production
                },
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct",  # Using Llama 3.3 70B model
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extract the analysis from the AI response
            ai_analysis = json.loads(result["choices"][0]["message"]["content"])
            
            # Generate all visualizations in the response
            visualization_paths = []

            if "visualizations" in ai_analysis and isinstance(ai_analysis["visualizations"], list):
                for i, viz_item in enumerate(ai_analysis["visualizations"]):
                    try:
                        # Debug visualization item
                        print(f"Processing visualization {i+1}:", viz_item)
                        
                        viz_code = None
                        if "code" in viz_item and viz_item["code"]:
                            viz_code = viz_item["code"]
                        
                        # Create a namespace with required libraries
                        viz_namespace = {
                            "pd": pd, 
                            "plt": plt,
                            "px": px,
                            "df": df,
                            "BytesIO": BytesIO,
                            "np": __import__('numpy'),
                            "sns": __import__('seaborn')
                        }
                        
                        # If code is missing or empty, generate a default visualization
                        if not viz_code or len(viz_code.strip()) < 10:
                            if i == 0:  # First viz - distribution of a numeric column
                                numeric_cols = df.select_dtypes(include=['number']).columns
                                if len(numeric_cols) > 0:
                                    viz_code = f"""
import seaborn as sns
plt.figure(figsize=(10, 6))
sns.histplot(df['{numeric_cols[0]}'], kde=True)
plt.title('Distribution of {numeric_cols[0]}')
plt.xlabel('{numeric_cols[0]}')
plt.ylabel('Count')
plt.tight_layout()
"""
                                    viz_item["title"] = f"Distribution of {numeric_cols[0]}"
                                    viz_item["description"] = f"Histogram showing the distribution of {numeric_cols[0]} values"
                            
                            elif i == 1:  # Second viz - correlation heatmap
                                numeric_df = df.select_dtypes(include=['number'])
                                if numeric_df.shape[1] > 1:
                                    viz_code = """
import seaborn as sns
plt.figure(figsize=(12, 10))
corr = df.select_dtypes(include=['number']).corr()
mask = np.triu(np.ones_like(corr, dtype=bool))
sns.heatmap(corr, mask=mask, annot=True, cmap='coolwarm', fmt='.2f', linewidths=0.5)
plt.title('Correlation Heatmap')
plt.tight_layout()
"""
                                    viz_item["title"] = "Correlation Heatmap"
                                    viz_item["description"] = "Heatmap showing correlations between numeric variables"
                        
                        if viz_code:
                            # Try to execute the visualization code
                            exec(viz_code, viz_namespace)
                            
                            # Save the visualization
                            vis_id = str(uuid.uuid4())
                            output_path = OUTPUT_DIR / f"{vis_id}.png"
                            
                            # If matplotlib was used (this will catch most visualizations)
                            if "plt" in viz_namespace and "plt" in viz_code:
                                plt.savefig(str(output_path), dpi=300, bbox_inches='tight')
                                plt.close('all')  # Close all figures to avoid memory issues
                                visualization_paths.append({
                                    "path": f"/temp/outputs/{vis_id}.png",
                                    "title": viz_item.get("title", f"Visualization {i+1}"),
                                    "description": viz_item.get("description", "")
                                })
                                continue
                            
                            # If plotly was used
                            if "px" in viz_code or "go." in viz_code or "fig" in viz_namespace:
                                if "fig" in viz_namespace:
                                    viz_namespace["fig"].write_image(str(output_path))
                                    visualization_paths.append({
                                        "path": f"/temp/outputs/{vis_id}.png",
                                        "title": viz_item.get("title", f"Visualization {i+1}"),
                                        "description": viz_item.get("description", "")
                                    })
                                
                            # If neither method worked, generate a fallback visualization
                            elif not visualization_paths:
                                # Create a simple fallback visualization
                                plt.figure(figsize=(10, 6))
                                if df.select_dtypes(include=['number']).shape[1] > 0:
                                    numeric_col = df.select_dtypes(include=['number']).columns[0]
                                    plt.hist(df[numeric_col], bins=20, alpha=0.7)
                                    plt.title(f"Distribution of {numeric_col}")
                                    plt.xlabel(numeric_col)
                                    plt.ylabel("Frequency")
                                else:
                                    # For categorical data
                                    cat_col = df.columns[0]
                                    counts = df[cat_col].value_counts().head(10)
                                    counts.plot(kind='bar')
                                    plt.title(f"Top 10 values in {cat_col}")
                                    plt.xticks(rotation=45)
                                
                                plt.tight_layout()
                                plt.savefig(str(output_path), dpi=300, bbox_inches='tight')
                                plt.close()
                                visualization_paths.append({
                                    "path": f"/temp/outputs/{vis_id}.png",
                                    "title": f"Fallback Visualization for {viz_item.get('title', f'Visualization {i+1}')}",
                                    "description": "Automatically generated fallback visualization"
                                })
                    
                    except Exception as e:
                        print(f"Visualization error for item {i+1}: {str(e)}")
                        try:
                            # Try to generate a fallback viz on error
                            vis_id = str(uuid.uuid4())
                            output_path = OUTPUT_DIR / f"{vis_id}.png"
                            
                            plt.figure(figsize=(10, 6))
                            plt.text(0.5, 0.5, f"Error generating visualization:\n{str(e)}", 
                                     ha='center', va='center', fontsize=12, wrap=True)
                            plt.axis('off')
                            plt.savefig(str(output_path), dpi=300)
                            plt.close()
                            
                            visualization_paths.append({
                                "path": f"/temp/outputs/{vis_id}.png",
                                "title": f"Error in Visualization {i+1}",
                                "description": f"Error: {str(e)}"
                            })
                        except Exception:
                            pass

            # If we still don't have any visualizations, add default ones
            if not visualization_paths:
                try:
                    # 1. Add a data overview visualization
                    vis_id = str(uuid.uuid4())
                    output_path = OUTPUT_DIR / f"{vis_id}.png"
                    
                    plt.figure(figsize=(12, 8))
                    
                    # Create a 2x2 subplot layout
                    plt.subplot(2, 2, 1)
                    if df.select_dtypes(include=['number']).shape[1] > 0:
                        numeric_col = df.select_dtypes(include=['number']).columns[0]
                        plt.hist(df[numeric_col], bins=20, alpha=0.7)
                        plt.title(f"Distribution of {numeric_col}")
                    else:
                        plt.text(0.5, 0.5, "No numeric columns found", ha='center', va='center')
                        plt.axis('off')
                    
                    plt.subplot(2, 2, 2)
                    if df.select_dtypes(include=['number']).shape[1] > 1:
                        numeric_cols = df.select_dtypes(include=['number']).columns
                        plt.scatter(df[numeric_cols[0]], df[numeric_cols[1]])
                        plt.xlabel(numeric_cols[0])
                        plt.ylabel(numeric_cols[1])
                        plt.title(f"Scatter: {numeric_cols[0]} vs {numeric_cols[1]}")
                    else:
                        plt.text(0.5, 0.5, "Insufficient numeric columns for scatter", ha='center', va='center')
                        plt.axis('off')
                    
                    plt.subplot(2, 2, 3)
                    if df.select_dtypes(include=['object', 'category']).shape[1] > 0:
                        cat_col = df.select_dtypes(include=['object', 'category']).columns[0]
                        df[cat_col].value_counts().head(5).plot(kind='bar')
                        plt.title(f"Top 5 values in {cat_col}")
                        plt.xticks(rotation=45)
                    else:
                        plt.text(0.5, 0.5, "No categorical columns found", ha='center', va='center')
                        plt.axis('off')
                    
                    plt.subplot(2, 2, 4)
                    plt.text(0.5, 0.5, f"Dataset Summary:\nRows: {df.shape[0]}\nColumns: {df.shape[1]}\nMissing Values: {df.isna().sum().sum()}", 
                             ha='center', va='center', fontsize=12)
                    plt.axis('off')
                    
                    plt.tight_layout()
                    plt.savefig(str(output_path), dpi=300)
                    plt.close()
                    
                    visualization_paths.append({
                        "path": f"/temp/outputs/{vis_id}.png",
                        "title": "Data Overview",
                        "description": "A summary of key characteristics in the dataset"
                    })
                    
                    # 2. Add a correlation heatmap if possible
                    if df.select_dtypes(include=['number']).shape[1] > 1:
                        vis_id = str(uuid.uuid4())
                        output_path = OUTPUT_DIR / f"{vis_id}.png"
                        
                        plt.figure(figsize=(10, 8))
                        corr = df.select_dtypes(include=['number']).corr()
                        sns = __import__('seaborn')
                        sns.heatmap(corr, annot=True, cmap='coolwarm', fmt='.2f')
                        plt.title('Correlation Heatmap')
                        plt.tight_layout()
                        plt.savefig(str(output_path), dpi=300)
                        plt.close()
                        
                        visualization_paths.append({
                            "path": f"/temp/outputs/{vis_id}.png",
                            "title": "Correlation Heatmap",
                            "description": "Heatmap showing correlations between numeric variables"
                        })
                
                except Exception as e:
                    print(f"Error creating default visualizations: {str(e)}")
            
            def format_content(content):
                """Format content for HTML, handling different types"""
                if isinstance(content, str):
                    return content.replace("\n", "<br>")
                elif isinstance(content, dict) or isinstance(content, list):
                    return json.dumps(content, indent=2).replace("\n", "<br>").replace(" ", "&nbsp;")
                else:
                    return str(content).replace("\n", "<br>")

            # Create a dashboard HTML
            dashboard_id = str(uuid.uuid4())
            dashboard_path = OUTPUT_DIR / f"{dashboard_id}.html"

            with open(dashboard_path, "w") as f:
                f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Automated EDA Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; }
        .viz-card { margin-bottom: 20px; }
        .viz-img { max-width: 100%; border-radius: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .section { margin-bottom: 30px; padding: 20px; border-radius: 10px; background-color: #f8f9fa; }
        pre { background-color: #f0f0f0; padding: 15px; border-radius: 5px; overflow-x: auto; }
        h1, h2 { color: #0d6efd; }
        .nav-tabs { margin-bottom: 20px; }
        code { white-space: pre-wrap; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row mb-4">
            <div class="col">
                <h1>Automated EDA Dashboard</h1>
                <p class="lead">Exploratory Data Analysis for: """ + data["filename"] + """</p>
                <p>Dataset Shape: """ + str(df.shape[0]) + """ rows × """ + str(df.shape[1]) + """ columns</p>
            </div>
        </div>

        <ul class="nav nav-tabs" id="myTab" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="summary-tab" data-bs-toggle="tab" data-bs-target="#summary" type="button" role="tab">Summary</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="visualizations-tab" data-bs-toggle="tab" data-bs-target="#visualizations" type="button" role="tab">Visualizations</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="preprocessing-tab" data-bs-toggle="tab" data-bs-target="#preprocessing" type="button" role="tab">Preprocessing</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="insights-tab" data-bs-toggle="tab" data-bs-target="#insights" type="button" role="tab">Insights</button>
            </li>
        </ul>

        <div class="tab-content" id="myTabContent">
            <!-- Summary Tab -->
            <div class="tab-pane fade show active" id="summary" role="tabpanel">
                <div class="row">
                    <div class="col-md-6">
                        <div class="section">
                            <h2>Data Quality Assessment</h2>
                            <div class="card">
                                <div class="card-body">
                                    """ + format_content(ai_analysis.get("data_quality", "No data quality assessment available")) + """
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="section">
                            <h2>Key Statistics</h2>
                            <div class="card">
                                <div class="card-body">
                                    """ + format_content(ai_analysis.get("statistics", "No statistics available")) + """
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Correlation Analysis</h2>
                    <div class="card">
                        <div class="card-body">
                            """ + format_content(ai_analysis.get("correlations", "No correlation analysis available")) + """
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Patterns and Trends</h2>
                    <div class="card">
                        <div class="card-body">
                            """ + format_content(ai_analysis.get("patterns", "No patterns identified")) + """
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Visualizations Tab -->
            <div class="tab-pane fade" id="visualizations" role="tabpanel">
                <div class="section">
                    <h2>Key Visualizations</h2>
                    <div class="row">
""")

                # Add each visualization
                if visualization_paths:
                    for viz in visualization_paths:
                        f.write(f"""
                <div class="col-md-6">
                    <div class="card viz-card">
                        <div class="card-header">
                            <h5>{viz["title"]}</h5>
                        </div>
                        <div class="card-body text-center">
                            <img src="{viz["path"]}" alt="{viz["title"]}" class="viz-img">
                            <p class="mt-3">{viz.get("description", "")}</p>
                        </div>
                    </div>
                </div>
""")
                else:
                    f.write("""
                <div class="col-12">
                    <div class="alert alert-info">
                        No visualizations were generated. This could be because the data doesn't lend itself to visualization,
                        or there was an error in generating the visualizations.
                    </div>
                </div>
""")

                f.write("""
                </div>
            </div>
            
            <!-- Preprocessing Tab -->
            <div class="tab-pane fade" id="preprocessing" role="tabpanel">
                <div class="section">
                    <h2>Recommended Preprocessing Steps</h2>
                    <div class="card">
                        <div class="card-body">
                            """ + format_content(ai_analysis.get("preprocessing", "No preprocessing recommendations available")) + """
                        </div>
                    </div>
""")

                # Add preprocessed data info if available
                if "preprocessed_data_info" in ai_analysis:
                    f.write(f"""
                <div class="mt-4">
                    <h3>Preprocessing Results</h3>
                    <p>Original Shape: {ai_analysis["preprocessed_data_info"]["original_shape"]}</p>
                    <p>Preprocessed Shape: {ai_analysis["preprocessed_data_info"]["preprocessed_shape"]}</p>
                    <h4>Changes:</h4>
                    <ul>
""")
                    # Handle case where changes might be empty
                    if ai_analysis["preprocessed_data_info"]["changes"]:
                        for change in ai_analysis["preprocessed_data_info"]["changes"]:
                            f.write(f"<li>{change}</li>")
                    else:
                        f.write("<li>No significant data type changes detected</li>")
                    f.write("""
                    </ul>
                </div>
""")

                # Include preprocessing errors if any
                if "preprocessing_error" in ai_analysis:
                    f.write(f"""
                <div class="alert alert-warning mt-3">
                    <strong>Warning:</strong> There was an error during preprocessing: {ai_analysis["preprocessing_error"]}
                </div>
""")

                f.write("""
            </div>
            
            <!-- Insights Tab -->
            <div class="tab-pane fade" id="insights" role="tabpanel">
                <div class="section">
                    <h2>Key Insights</h2>
                    <div class="card">
                        <div class="card-body">
                            """ + format_content(ai_analysis.get("insights", "No insights available")) + """
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
""")
            
            # Store dashboard path in data_store
            data_store[file_id]["dashboard"] = f"/temp/outputs/{dashboard_id}.html"
            
            return {
                "dashboard_url": f"/temp/outputs/{dashboard_id}.html",
                "analysis": {
                    "data_quality": ai_analysis.get("data_quality", ""),
                    "statistics": ai_analysis.get("statistics", ""),
                    "correlations": ai_analysis.get("correlations", ""),
                    "patterns": ai_analysis.get("patterns", ""),
                    "insights": ai_analysis.get("insights", "")
                },
                "visualizations": visualization_paths
            }
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, 
                               detail=f"Error from OpenRouter API: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error analyzing data: {str(e)}")

@app.get("/temp/outputs/{filename}")
async def get_output_file(filename: str):
    """Serve output files (visualizations and reports)"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(str(file_path))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)