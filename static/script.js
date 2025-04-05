document.addEventListener('DOMContentLoaded', function() {
    // Global variables
    let fileId = null;
    let visualizationPaths = [];
    
    // Form elements
    const uploadForm = document.getElementById('uploadForm');
    const analysisForm = document.getElementById('analysisForm');
    const vizForm = document.getElementById('vizForm');
    const generateReportBtn = document.getElementById('generateReportBtn');
    
    // Info display elements
    const dataInfo = document.getElementById('dataInfo');
    const filename = document.getElementById('filename');
    const columnsList = document.getElementById('columnsList');
    const previewHeader = document.getElementById('previewHeader');
    const previewBody = document.getElementById('previewBody');
    
    // Analysis elements
    const analyzeBtn = document.getElementById('analyzeBtn');
    const analysisResult = document.getElementById('analysisResult');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const analysisContent = document.getElementById('analysisContent');
    const insightsContent = document.getElementById('insightsContent');
    const visualizationContainer = document.getElementById('visualizationContainer');
    
    // Visualization elements
    const vizType = document.getElementById('vizType');
    const xColumn = document.getElementById('xColumn');
    const yColumn = document.getElementById('yColumn');
    const colorBy = document.getElementById('colorBy');
    const createVizBtn = document.getElementById('createVizBtn');
    const customVizContainer = document.getElementById('customVizContainer');
    
    // Handle file upload
    uploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const fileInput = document.getElementById('fileInput');
        const file = fileInput.files[0];
        
        if (!file) {
            alert('Please select a file');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Error uploading file');
            }
            
            const data = await response.json();
            fileId = data.file_id;
            
            // Display file information
            dataInfo.style.display = 'block';
            filename.textContent = data.filename;
            
            // Populate columns list
            columnsList.innerHTML = '';
            data.columns.forEach(column => {
                const li = document.createElement('li');
                li.textContent = column;
                columnsList.appendChild(li);
            });
            
            // Create preview table
            previewHeader.innerHTML = '';
            previewBody.innerHTML = '';
            
            // Add header row
            data.columns.forEach(column => {
                const th = document.createElement('th');
                th.textContent = column;
                previewHeader.appendChild(th);
            });
            
            // Add data rows
            data.preview.forEach(row => {
                const tr = document.createElement('tr');
                data.columns.forEach(column => {
                    const td = document.createElement('td');
                    td.textContent = row[column] !== null && row[column] !== undefined ? row[column] : '';
                    tr.appendChild(td);
                });
                previewBody.appendChild(tr);
            });
            
            // Enable analysis button
            analyzeBtn.disabled = false;
            
            // Populate visualization dropdowns
            populateColumnDropdowns(data.columns);
            
            // Enable visualization controls
            vizType.disabled = false;
            xColumn.disabled = false;
            yColumn.disabled = false;
            colorBy.disabled = false;
            createVizBtn.disabled = false;

            // Automatically trigger EDA dashboard creation
            if (fileId) {
                // First check if dashboard container already exists and remove it
                const existingDashboard = document.getElementById('dashboardContainer');
                if (existingDashboard) {
                    existingDashboard.remove();
                }
                
                // Create dashboard container and insert it after dataInfo
                const dashboardContainer = document.createElement('div');
                dashboardContainer.id = 'dashboardContainer';
                dashboardContainer.className = 'card mb-4';
                dashboardContainer.innerHTML = `
                    <div class="card-header">
                        <h5 class="card-title">Automated EDA Dashboard</h5>
                    </div>
                    <div class="card-body text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-3">Creating your EDA dashboard with AI... This may take a minute.</p>
                    </div>
                `;
                
                // Insert after dataInfo
                dataInfo.parentNode.insertBefore(dashboardContainer, dataInfo.nextSibling);
                
                // Call the auto-analyze endpoint
                const autoAnalyzeFormData = new FormData();
                autoAnalyzeFormData.append('file_id', fileId);
                
                fetch('/api/auto-analyze', {
                    method: 'POST',
                    body: autoAnalyzeFormData
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.detail || 'Error creating dashboard');
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    // Show dashboard link
                    dashboardContainer.innerHTML = `
                        <div class="card-header">
                            <h5 class="card-title">Automated EDA Dashboard</h5>
                        </div>
                        <div class="card-body text-center">
                            <p>Your EDA dashboard is ready!</p>
                            <a href="${data.dashboard_url}" target="_blank" class="btn btn-primary">
                                Open Dashboard
                            </a>
                            <p class="mt-2 text-muted">The dashboard contains ${data.visualizations.length} visualizations and comprehensive analysis.</p>
                        </div>
                    `;
                })
                .catch(error => {
                    dashboardContainer.innerHTML = `
                        <div class="card-header">
                            <h5 class="card-title">Automated EDA Dashboard</h5>
                        </div>
                        <div class="card-body">
                            <div class="alert alert-danger">
                                Dashboard creation failed: ${error.message}
                            </div>
                            <button class="btn btn-outline-primary mt-2" id="retryDashboardBtn">Retry</button>
                        </div>
                    `;
                    
                    // Add retry functionality
                    document.getElementById('retryDashboardBtn').addEventListener('click', function() {
                        // Reset dashboard container
                        dashboardContainer.innerHTML = `
                            <div class="card-header">
                                <h5 class="card-title">Automated EDA Dashboard</h5>
                            </div>
                            <div class="card-body text-center">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Loading...</span>
                                </div>
                                <p class="mt-3">Retrying dashboard creation...</p>
                            </div>
                        `;
                        
                        // Call auto-analyze again
                        const retryFormData = new FormData();
                        retryFormData.append('file_id', fileId);
                        
                        fetch('/api/auto-analyze', {
                            method: 'POST',
                            body: retryFormData
                        })
                        .then(response => {
                            if (!response.ok) {
                                return response.json().then(data => {
                                    throw new Error(data.detail || 'Error creating dashboard');
                                });
                            }
                            return response.json();
                        })
                        .then(data => {
                            // Show dashboard link after retry
                            dashboardContainer.innerHTML = `
                                <div class="card-header">
                                    <h5 class="card-title">Automated EDA Dashboard</h5>
                                </div>
                                <div class="card-body text-center">
                                    <p>Your EDA dashboard is ready!</p>
                                    <a href="${data.dashboard_url}" target="_blank" class="btn btn-primary">
                                        Open Dashboard
                                    </a>
                                    <p class="mt-2 text-muted">The dashboard contains ${data.visualizations.length} visualizations and comprehensive analysis.</p>
                                </div>
                            `;
                        })
                        .catch(error => {
                            dashboardContainer.innerHTML = `
                                <div class="card-header">
                                    <h5 class="card-title">Automated EDA Dashboard</h5>
                                </div>
                                <div class="card-body">
                                    <div class="alert alert-danger">
                                        Dashboard creation failed again: ${error.message}
                                    </div>
                                    <p>Please try analyzing the data manually using the AI Analysis section below.</p>
                                </div>
                            `;
                        });
                    });
                    
                    console.error('Dashboard error:', error);
                });
            }
            
        } catch (error) {
            alert(`Upload failed: ${error.message}`);
            console.error('Upload error:', error);
        }
    });
    
    // Handle AI analysis
    analysisForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (!fileId) {
            alert('Please upload a file first');
            return;
        }
        
        const query = document.getElementById('queryInput').value.trim();
        
        if (!query) {
            alert('Please enter a query');
            return;
        }
        
        // Show loading spinner
        analysisResult.style.display = 'block';
        loadingSpinner.style.display = 'block';
        analysisContent.innerHTML = '';
        insightsContent.innerHTML = '';
        visualizationContainer.innerHTML = '';
        generateReportBtn.style.display = 'none';
        
        const formData = new FormData();
        formData.append('file_id', fileId);
        formData.append('query', query);
        
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Analysis failed');
            }
            
            const data = await response.json();
            
            // Hide loading spinner
            loadingSpinner.style.display = 'none';
            
            // Display analysis
            analysisContent.innerHTML = `<h6>Analysis:</h6><div>${formatText(data.analysis)}</div>`;
            
            // Display insights
            insightsContent.innerHTML = `<h6>Insights:</h6><div>${formatText(data.insights)}</div>`;
            
            // Display visualization if available
            if (data.visualization) {
                const img = document.createElement('img');
                img.src = data.visualization;
                img.alt = 'AI-generated visualization';
                img.className = 'img-fluid mt-3';
                visualizationContainer.innerHTML = '<h6>AI-Generated Visualization:</h6>';
                visualizationContainer.appendChild(img);
                
                // Add to visualization paths for report generation
                visualizationPaths.push(data.visualization);
            }
            
            // Show report generation button
            generateReportBtn.style.display = 'block';
            
        } catch (error) {
            loadingSpinner.style.display = 'none';
            analysisContent.innerHTML = `<div class="alert alert-danger">Analysis failed: ${error.message}</div>`;
            console.error('Analysis error:', error);
        }
    });
    
    // Handle custom visualization
    vizForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (!fileId) {
            alert('Please upload a file first');
            return;
        }
        
        const vizTypeValue = vizType.value;
        const xColumnValue = xColumn.value;
        const yColumnValue = yColumn.value;
        const colorByValue = colorBy.value;
        
        const formData = new FormData();
        formData.append('file_id', fileId);
        formData.append('viz_type', vizTypeValue);
        formData.append('x_column', xColumnValue);
        
        if (yColumnValue) {
            formData.append('y_column', yColumnValue);
        }
        
        if (colorByValue) {
            formData.append('color_by', colorByValue);
        }
        
        try {
            customVizContainer.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
            
            const response = await fetch('/api/visualize', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Visualization creation failed');
            }
            
            const data = await response.json();
            
            // Display visualization
            if (data.visualization) {
                const img = document.createElement('img');
                img.src = data.visualization;
                img.alt = 'Custom visualization';
                img.className = 'img-fluid mt-3';
                customVizContainer.innerHTML = '';
                customVizContainer.appendChild(img);
                
                // Add to visualization paths for report generation
                visualizationPaths.push(data.visualization);
                
                // Show report generation button
                generateReportBtn.style.display = 'block';
            }
            
        } catch (error) {
            customVizContainer.innerHTML = `<div class="alert alert-danger">Visualization failed: ${error.message}</div>`;
            console.error('Visualization error:', error);
        }
    });
    
    // Handle report generation
    generateReportBtn.addEventListener('click', async function() {
        if (!fileId) {
            alert('Please upload a file first');
            return;
        }
        
        const analysisText = analysisContent.textContent + '\n\n' + insightsContent.textContent;
        
        const formData = new FormData();
        formData.append('file_id', fileId);
        formData.append('analysis_text', analysisText);
        
        visualizationPaths.forEach(path => {
            formData.append('visualization_paths', path);
        });
        
        try {
            generateReportBtn.disabled = true;
            generateReportBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Generating...';
            
            const response = await fetch('/api/generate-report', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Report generation failed');
            }
            
            const data = await response.json();
            
            // Open the PDF in a new tab
            if (data.report) {
                window.open(data.report, '_blank');
            }
            
        } catch (error) {
            alert(`Report generation failed: ${error.message}`);
            console.error('Report generation error:', error);
        } finally {
            generateReportBtn.disabled = false;
            generateReportBtn.innerHTML = 'Generate PDF Report';
        }
    });
    
    // Helper function to populate column dropdowns
    function populateColumnDropdowns(columns) {
        // Clear existing options
        xColumn.innerHTML = '';
        yColumn.innerHTML = '<option value="">None</option>';
        colorBy.innerHTML = '<option value="">None</option>';
        
        // Add columns to dropdowns
        columns.forEach(column => {
            const xOption = document.createElement('option');
            xOption.value = column;
            xOption.textContent = column;
            xColumn.appendChild(xOption);
            
            const yOption = document.createElement('option');
            yOption.value = column;
            yOption.textContent = column;
            yColumn.appendChild(yOption);
            
            const colorOption = document.createElement('option');
            colorOption.value = column;
            colorOption.textContent = column;
            colorBy.appendChild(colorOption);
        });
    }
    
    // Helper function to format text with paragraphs and code blocks
    function formatText(text) {
        if (!text) return '';
        
        // Replace newlines with <br> tags
        let formatted = text.replace(/\n/g, '<br>');
        
        // Format code blocks (simple implementation)
        formatted = formatted.replace(/```(.*?)```/gs, function(match, code) {
            return `<pre><code>${code.trim()}</code></pre>`;
        });
        
        return formatted;
    }
});