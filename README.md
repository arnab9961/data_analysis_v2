# AI-Powered Data Analysis Workspace Backend

## Overview
This backend is built using FastAPI and serves as the API for the AI-powered data analysis workspace. It provides endpoints for data analysis, including functionalities for handling file uploads, data processing, and visualization.

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd ai-data-analysis-workspace/backend
   ```

2. **Create a Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the FastAPI Application**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Access the API Documentation**
   Open your browser and navigate to `http://127.0.0.1:8000/docs` to view the interactive API documentation.

## Features

- **Data Analysis Endpoints**: Includes endpoints for Llama 3.3 completions, file uploads for CSV/Excel data, and data visualization.
- **CORS Configuration**: Allows cross-origin requests to enable frontend-backend communication.
- **Modular Structure**: Organized into packages for easy maintenance and scalability.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.