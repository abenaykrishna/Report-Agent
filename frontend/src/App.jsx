import React, { useState, useEffect, useRef } from 'react';
import { 
  ThemeProvider, 
  createTheme, 
  Box, 
  Container, 
  Grid, 
  Card, 
  CardContent, 
  Typography, 
  TextField, 
  Button, 
  LinearProgress, 
  CircularProgress, 
  Tabs, 
  Tab, 
  Table, 
  TableBody, 
  TableCell, 
  TableContainer, 
  TableHead, 
  TableRow, 
  Paper, 
  Snackbar, 
  Alert, 
  Chip, 
  IconButton,
  Divider,
  Paper as MuiPaper,
  List,
  ListItem,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import { 
  CloudUpload as CloudUploadIcon, 
  Delete as DeleteIcon, 
  Description as DescriptionIcon, 
  Download as DownloadIcon, 
  Refresh as RefreshIcon, 
  PlayArrow as PlayArrowIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Timeline as TimelineIcon,
  Storage as StorageIcon,
  HourglassEmpty as HourglassEmptyIcon,
  TableChart as TableChartIcon,
  Search as SearchIcon,
  Check as CheckIcon,
  ArrowForward as ArrowForwardIcon,
  Dashboard as DashboardIcon
} from '@mui/icons-material';
import axios from 'axios';
import './App.css';

// Premium Theme Configuration (Enterprise Slate Dark/Light style)
const theme = createTheme({
  palette: {
    primary: {
      main: '#1B365D', // Corporate Deep Navy
      light: '#3A5B8C',
      dark: '#0F213F',
    },
    secondary: {
      main: '#0284c7', // Slate Blue
      light: '#38bdf8',
      dark: '#0369a1',
    },
    success: {
      main: '#10b981', // Emerald Green
    },
    error: {
      main: '#ef4444', // Coral Red
    },
    background: {
      default: '#f8fafc', // Light Soft Slate
      paper: '#ffffff',
    },
    text: {
      primary: '#0f172a',
      secondary: '#475569',
    },
  },
  typography: {
    fontFamily: '"Inter", "Segoe UI", "Roboto", sans-serif',
    h4: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em',
    },
    h5: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    h6: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    button: {
      textTransform: 'none',
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '8px 16px',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)',
          border: '1px solid #f1f5f9',
        },
      },
    },
  },
});

const ALL_STAGES = [
  "Reading input...",
  "Extracting report requirements...",
  "Searching Dataplex Metadata...",
  "Selecting optimal source tables...",
  "Discovering joins...",
  "Generating SQL...",
  "Executing BigQuery query...",
  "Searching Dataplex Lineage...",
  "Generating Metadata...",
  "Generating Transformation Mapping...",
  "Generating Dashboard...",
  "Generating Excel report...",
  "Completed."
];

export default function App() {
  const [tabValue, setTabValue] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [templatePath, setTemplatePath] = useState('');
  const [uploading, setUploading] = useState(false);
  
  // Progress states
  const [generating, setGenerating] = useState(false);
  const [taskId, setTaskId] = useState('');
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressStage, setProgressStage] = useState('');
  const [elapsedTime, setElapsedTime] = useState(0);
  const [taskStatus, setTaskStatus] = useState(null);
  
  // Preview
  const [previewData, setPreviewData] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Snackbar notifications
  const [notification, setNotification] = useState({
    open: false,
    message: '',
    severity: 'success'
  });

  const timerRef = useRef(null);
  const dragCounter = useRef(0);
  const [dragActive, setDragActive] = useState(false);

  // Auto scroll down in progress logs
  const logEndRef = useRef(null);

  // Polling control
  useEffect(() => {
    let pollingInterval;
    if (generating && taskId) {
      pollingInterval = setInterval(async () => {
        try {
          const res = await axios.get(`/api/tasks/${taskId}`);
          const task = res.data;
          
          if (task.progress_stage) {
            setProgressStage(task.progress_stage);
          }
          if (task.progress_percent !== undefined) {
            setProgressPercent(task.progress_percent);
          }

          if (task.status === 'completed') {
            clearInterval(pollingInterval);
            clearInterval(timerRef.current);
            setGenerating(false);
            setTaskStatus(task);
            showNotification('Report generated successfully!', 'success');
            
            // Fetch preview data
            fetchPreview(taskId);
            
            // Automatically redirect to output page
            setTabValue(1);
          } else if (task.status === 'failed') {
            clearInterval(pollingInterval);
            clearInterval(timerRef.current);
            setGenerating(false);
            setTaskStatus(task);
            showNotification(task.error || 'Report generation failed.', 'error');
          }
        } catch (err) {
          console.error('Error polling status:', err);
          showNotification(err.response?.data?.detail || 'Failed to sync execution status with server.', 'error');
        }
      }, 1500);
    }

    return () => {
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, [generating, taskId]);

  // Elapsed timer
  useEffect(() => {
    if (generating) {
      timerRef.current = setInterval(() => {
        setElapsedTime(prev => prev + 0.1);
      }, 100);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [generating]);

  // Scroll to bottom of logs whenever active stage changes
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [progressStage]);

  const showNotification = (message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  };

  const handleTabChange = (event, newValue) => {
    // Only allow navigating to Output if taskStatus (success or failure) is available
    if (newValue === 1 && !taskStatus) {
      showNotification('Please submit a query or template and generate a report first.', 'warning');
      return;
    }
    setTabValue(newValue);
  };

  // Drag-and-drop handlers
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter") {
      dragCounter.current++;
      setDragActive(true);
    } else if (e.type === "dragleave" || e.type === "drop") {
      dragCounter.current--;
      if (dragCounter.current === 0) {
        setDragActive(false);
      }
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    dragCounter.current = 0;

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      handleFileSelected(file);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const handleFileSelected = async (file) => {
    const name = file.name.toLowerCase();
    if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
      showNotification('Unsupported file type. Only Excel templates (.xlsx, .xls) are allowed.', 'error');
      return;
    }

    setSelectedFile(file);
    setUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post('/api/upload-template', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setTemplatePath(res.data.template_path);
      showNotification(`Template file "${file.name}" uploaded successfully!`, 'success');
    } catch (err) {
      console.error(err);
      setSelectedFile(null);
      setTemplatePath('');
      showNotification(err.response?.data?.detail || 'Failed to upload template workbook.', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setTemplatePath('');
    showNotification('Template workbook removed.', 'info');
  };

  const handleGenerateReport = async () => {
    if (!prompt.trim() && !templatePath) {
      showNotification('Validation Error: Please write a natural language request or drag-and-drop an Excel template file.', 'error');
      return;
    }

    setGenerating(true);
    setTaskId('');
    setTaskStatus(null);
    setProgressPercent(5);
    setProgressStage('Reading input...');
    setElapsedTime(0);
    setPreviewData(null);

    try {
      const res = await axios.post('/api/generate-report', {
        prompt: prompt.trim() || null,
        template_path: templatePath || null
      });
      setTaskId(res.data.task_id);
    } catch (err) {
      console.error(err);
      setGenerating(false);
      showNotification(err.response?.data?.detail || 'Failed to submit report generation request.', 'error');
    }
  };

  const fetchPreview = async (id) => {
    setLoadingPreview(true);
    try {
      const res = await axios.get(`/api/tasks/${id}/preview`);
      setPreviewData(res.data);
    } catch (err) {
      console.error(err);
      showNotification('Failed to generate report preview in table: ' + (err.response?.data?.detail || err.message), 'error');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleDownload = () => {
    if (!taskId) return;
    const backendUrl = window.location.port === '5173' 
      ? 'http://localhost:8000' 
      : '';
    window.open(`${backendUrl}/api/tasks/${taskId}/download`, '_blank');
  };

  const handleGenerateAnother = () => {
    setPrompt('');
    setSelectedFile(null);
    setTemplatePath('');
    setTaskId('');
    setTaskStatus(null);
    setPreviewData(null);
    setElapsedTime(0);
    setProgressPercent(0);
    setProgressStage('');
    setTabValue(0); // Go back to Input page
  };

  // Determine stage icon state
  const getStageIcon = (stageName) => {
    const stageIndex = ALL_STAGES.indexOf(stageName);
    const activeIndex = ALL_STAGES.indexOf(progressStage);

    if (taskStatus?.status === 'completed') {
      return <CheckCircleIcon sx={{ color: 'success.main', fontSize: 20 }} />;
    }
    if (taskStatus?.status === 'failed') {
      if (stageIndex < activeIndex) return <CheckCircleIcon sx={{ color: 'success.main', fontSize: 20 }} />;
      if (stageIndex === activeIndex) return <CancelIcon sx={{ color: 'error.main', fontSize: 20 }} />;
      return <HourglassEmptyIcon sx={{ color: 'text.disabled', fontSize: 20 }} />;
    }

    if (stageIndex < activeIndex) {
      return <CheckCircleIcon sx={{ color: 'success.main', fontSize: 20 }} />;
    } else if (stageIndex === activeIndex) {
      return <CircularProgress size={18} thickness={5} sx={{ color: 'primary.main' }} />;
    } else {
      return <HourglassEmptyIcon sx={{ color: 'text.disabled', fontSize: 20 }} />;
    }
  };

  const getStageTextColor = (stageName) => {
    const stageIndex = ALL_STAGES.indexOf(stageName);
    const activeIndex = ALL_STAGES.indexOf(progressStage);

    if (taskStatus?.status === 'completed') return 'text.primary';
    if (stageIndex < activeIndex) return 'text.secondary';
    if (stageIndex === activeIndex) return 'primary.main';
    return 'text.disabled';
  };

  const getStageFontWeight = (stageName) => {
    return ALL_STAGES.indexOf(stageName) === ALL_STAGES.indexOf(progressStage) ? 600 : 400;
  };

  const exampleQueries = [
    "Generate Suppressed Policies Report for June 2025",
    "Generate Dropout Leads & Recovery Report",
    "Generate Policy Lapse Recovery Report",
    "Generate Premium Collection Report"
  ];

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
        
        {/* Header Bar */}
        <Paper elevation={0} sx={{ 
          bgcolor: 'primary.main', 
          color: 'white', 
          py: 2.5, 
          px: 3, 
          borderRadius: 0, 
          borderBottom: '1px solid rgba(255,255,255,0.1)' 
        }}>
          <Container maxWidth="xl">
            <Grid container alignItems="center" justifyContent="space-between">
              <Grid item>
                <Box display="flex" alignItems="center" gap={1.5}>
                  <DashboardIcon sx={{ fontSize: 32, color: 'secondary.light' }} />
                  <Box>
                    <Typography variant="h5" sx={{ fontFamily: 'Outfit', fontWeight: 800, color: 'white' }}>
                      Enterprise AI Report Generation Agent
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)', fontWeight: 500 }}>
                      Intelligent metadata schema lookup, lineages mapping, & Gemini SQL compiler
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              
              <Grid item>
                <Tabs 
                  value={tabValue} 
                  onChange={handleTabChange} 
                  textColor="inherit"
                  indicatorColor="secondary"
                  sx={{
                    '& .MuiTab-root': {
                      fontFamily: 'Outfit',
                      fontWeight: 600,
                      fontSize: '1rem',
                      opacity: 0.8,
                      px: 3,
                      '&.Mui-selected': {
                        opacity: 1,
                        color: 'white',
                      }
                    }
                  }}
                >
                  <Tab label="Input Config" />
                  <Tab label="Agent Output" disabled={!taskStatus} />
                </Tabs>
              </Grid>
            </Grid>
          </Container>
        </Paper>

        {/* Content Container */}
        <Container maxWidth="xl" sx={{ flexGrow: 1, py: 4 }}>
          
          {/* TAB 0: INPUT PAGE */}
          {tabValue === 0 && (
            <Grid container spacing={4} className="fade-in">
              
              {/* Query & Template Cards */}
              <Grid item xs={12} lg={generating ? 6 : 12}>
                <Grid container spacing={4}>
                  
                  {/* NL query card */}
                  <Grid item xs={12} md={generating ? 12 : 6}>
                    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                      <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', p: 3 }}>
                        <Box display="flex" alignItems="center" gap={1} mb={2}>
                          <SearchIcon sx={{ color: 'primary.main' }} />
                          <Typography variant="h6">Natural Language Query</Typography>
                        </Box>
                        
                        <Typography variant="body2" color="text.secondary" mb={2}>
                          Specify the parameters, target months, filters, or rules in plain language.
                        </Typography>
                        
                        <TextField
                          multiline
                          rows={6}
                          fullWidth
                          variant="outlined"
                          placeholder="Type report requests (e.g. Generate Suppressed Policies Report for June 2025)..."
                          value={prompt}
                          onChange={(e) => setPrompt(e.target.value)}
                          disabled={generating}
                          sx={{ 
                            flexGrow: 1, 
                            mb: 2.5,
                            '& .MuiOutlinedInput-root': {
                              backgroundColor: '#fafafa',
                              '&:hover fieldset': {
                                borderColor: 'secondary.main',
                              }
                            }
                          }}
                        />

                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }} mb={1}>
                          Suggested Examples:
                        </Typography>
                        <Box display="flex" flexWrap="wrap" gap={1}>
                          {exampleQueries.map((ex, index) => (
                            <Chip 
                              key={index} 
                              label={ex} 
                              onClick={() => !generating && setPrompt(ex)}
                              disabled={generating}
                              clickable
                              variant="outlined"
                              size="small"
                              sx={{ 
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                                '&:hover': {
                                  backgroundColor: 'secondary.light',
                                  color: 'white',
                                  borderColor: 'secondary.main'
                                }
                              }}
                            />
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Excel file upload card */}
                  <Grid item xs={12} md={generating ? 12 : 6}>
                    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                      <CardContent sx={{ p: 3, display: 'flex', flexDirection: 'column', height: '100%' }}>
                        <Box display="flex" alignItems="center" gap={1} mb={2}>
                          <DescriptionIcon sx={{ color: 'primary.main' }} />
                          <Typography variant="h6">Excel Report Template Upload</Typography>
                        </Box>
                        
                        <Typography variant="body2" color="text.secondary" mb={2}>
                          Provide a template file containing targeted column structures or metrics.
                        </Typography>

                        {/* Drag and Drop Zone */}
                        <Box 
                          onDragEnter={handleDrag}
                          onDragOver={handleDrag}
                          onDragLeave={handleDrag}
                          onDrop={handleDrop}
                          className={`drop-zone ${dragActive ? 'drop-zone-active' : ''}`}
                          sx={{
                            flexGrow: 1,
                            minHeight: 180,
                            border: '2px dashed',
                            borderColor: dragActive ? 'secondary.main' : '#cbd5e1',
                            borderRadius: 2,
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            p: 3,
                            bgcolor: dragActive ? '#eff6ff' : '#f8fafc',
                            textAlign: 'center',
                            cursor: generating ? 'not-allowed' : 'pointer'
                          }}
                          onClick={() => {
                            if (!generating && !selectedFile && !uploading) {
                              document.getElementById('excel-file-input').click();
                            }
                          }}
                        >
                          <input 
                            type="file" 
                            id="excel-file-input" 
                            style={{ display: 'none' }} 
                            accept=".xlsx, .xls"
                            onChange={handleFileChange}
                            disabled={generating}
                          />

                          {uploading ? (
                            <Box display="flex" flexDirection="column" alignItems="center" gap={2}>
                              <CircularProgress size={36} />
                              <Typography variant="body2" color="text.secondary">
                                Processing layout and cells structure...
                              </Typography>
                            </Box>
                          ) : selectedFile ? (
                            <Box display="flex" flexDirection="column" alignItems="center" gap={1.5}>
                              <DescriptionIcon sx={{ fontSize: 48, color: 'primary.main' }} />
                              <Box>
                                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                  {selectedFile.name}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {(selectedFile.size / 1024).toFixed(1)} KB
                                </Typography>
                              </Box>
                              
                              <Box display="flex" gap={1} mt={1}>
                                <Button 
                                  variant="outlined" 
                                  color="error" 
                                  size="small" 
                                  startIcon={<DeleteIcon />}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRemoveFile();
                                  }}
                                  disabled={generating}
                                >
                                  Remove File
                                </Button>
                                <Button
                                  variant="outlined"
                                  color="primary"
                                  size="small"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    document.getElementById('excel-file-input').click();
                                  }}
                                  disabled={generating}
                                >
                                  Replace
                                </Button>
                              </Box>
                            </Box>
                          ) : (
                            <Box display="flex" flexDirection="column" alignItems="center" gap={1}>
                              <CloudUploadIcon sx={{ fontSize: 48, color: '#94a3b8' }} />
                              <Typography variant="subtitle2" fontWeight={600}>
                                Drag and drop Excel template here
                              </Typography>
                              <Typography variant="caption" color="text.secondary" mb={1}>
                                Supported formats: .xlsx, .xls
                              </Typography>
                              <Button 
                                variant="contained" 
                                color="primary" 
                                size="small"
                                disabled={generating}
                                sx={{ pointerEvents: 'none' }} // Triggered by parent click
                              >
                                Browse Files
                              </Button>
                            </Box>
                          )}
                        </Box>

                        {/* Prioritization Warning */}
                        {prompt.trim() && templatePath && (
                          <Alert severity="warning" variant="outlined" sx={{ mt: 2, py: 0.5 }}>
                            Dual input detected. The uploaded Excel template will be prioritized.
                          </Alert>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Generate Button Row */}
                  <Grid item xs={12}>
                    <Box display="flex" justifyContent="center">
                      <Button
                        variant="contained"
                        color="secondary"
                        size="large"
                        className={!generating ? 'pulse-button' : ''}
                        disabled={generating || uploading}
                        startIcon={generating ? <CircularProgress size={20} color="inherit" /> : <PlayArrowIcon />}
                        onClick={handleGenerateReport}
                        sx={{ 
                          px: 6, 
                          py: 1.8, 
                          fontSize: '1.1rem',
                          borderRadius: 2.5,
                          boxShadow: '0 10px 15px -3px rgb(59 130 246 / 0.3)'
                        }}
                      >
                        {generating ? 'Processing Report Pipeline...' : 'Generate Analytical Report'}
                      </Button>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Progress Panel */}
              {generating && (
                <Grid item xs={12} lg={6} className="fade-in">
                  <Card sx={{ height: '100%', bgcolor: 'white', display: 'flex', flexDirection: 'column' }}>
                    <CardContent sx={{ p: 3, display: 'flex', flexDirection: 'column', height: '100%' }}>
                      
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1.5}>
                        <Typography variant="h6">Pipeline Execution Logs</Typography>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Chip 
                            label={`Elapsed: ${elapsedTime.toFixed(1)}s`} 
                            size="small" 
                            color="primary" 
                            variant="outlined" 
                          />
                        </Box>
                      </Box>
                      
                      <Divider sx={{ mb: 2.5 }} />

                      {/* Active Stage & Progress Bar */}
                      <Box mb={3.5}>
                        <Typography variant="subtitle2" color="text.secondary" mb={1}>
                          Current Stage: <span style={{ color: theme.palette.primary.main, fontWeight: 700 }}>{progressStage || 'Initializing...'}</span>
                        </Typography>
                        <LinearProgress 
                          variant="determinate" 
                          value={progressPercent} 
                          sx={{ 
                            height: 10, 
                            borderRadius: 5,
                            '& .MuiLinearProgress-bar': {
                              borderRadius: 5,
                              backgroundImage: 'linear-gradient(90deg, #3B82F6, #10B981)'
                            }
                          }}
                        />
                        <Box display="flex" justifyContent="space-between" mt={0.5}>
                          <Typography variant="caption" color="text.secondary">0%</Typography>
                          <Typography variant="caption" sx={{ fontWeight: 700 }} color="primary">{progressPercent}%</Typography>
                          <Typography variant="caption" color="text.secondary">100%</Typography>
                        </Box>
                      </Box>

                      {/* Log timeline */}
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                        Steps Progression Timeline
                      </Typography>
                      <Paper 
                        variant="outlined" 
                        sx={{ 
                          p: 2, 
                          bgcolor: '#f8fafc', 
                          flexGrow: 1, 
                          maxHeight: 280, 
                          overflowY: 'auto',
                          borderRadius: 2
                        }}
                      >
                        <List dense disablePadding>
                          {ALL_STAGES.map((stage, index) => {
                            const isPast = ALL_STAGES.indexOf(progressStage) > index;
                            const isActive = progressStage === stage;
                            return (
                              <ListItem 
                                key={index} 
                                sx={{ 
                                  py: 0.6, 
                                  px: 0.5,
                                  opacity: isPast || isActive ? 1 : 0.4
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 32 }}>
                                  {getStageIcon(stage)}
                                </ListItemIcon>
                                <ListItemText 
                                  primary={stage} 
                                  primaryTypographyProps={{
                                    variant: 'body2',
                                    fontWeight: getStageFontWeight(stage),
                                    color: getStageTextColor(stage)
                                  }}
                                />
                              </ListItem>
                            );
                          })}
                          <div ref={logEndRef} />
                        </List>
                      </Paper>

                    </CardContent>
                  </Card>
                </Grid>
              )}

            </Grid>
          )}

          {/* TAB 1: OUTPUT PAGE */}
          {tabValue === 1 && taskStatus && (
            <Box className="fade-in" sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              
              {/* Top Overview & Download Button */}
              <Card sx={{ bgcolor: 'white', p: 1 }}>
                <CardContent sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 3 }}>
                  <Box display="flex" alignItems="center" gap={2}>
                    <CheckCircleIcon sx={{ fontSize: 44, color: taskStatus.status === 'completed' ? 'success.main' : 'error.main' }} />
                    <Box>
                      <Typography variant="h5" color="primary.main">
                        {taskStatus.result?.report_name || 'Generated Report'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        File path: <span style={{ fontWeight: 500 }}>{taskStatus.result?.filename || 'N/A'}</span>
                      </Typography>
                    </Box>
                  </Box>
                  
                  <Box display="flex" gap={2}>
                    <Button
                      variant="contained"
                      color="success"
                      size="large"
                      startIcon={<DownloadIcon />}
                      onClick={handleDownload}
                      disabled={taskStatus.status !== 'completed'}
                      sx={{ py: 1.5, px: 3, boxShadow: '0 4px 6px -1px rgb(16 185 129 / 0.2)' }}
                    >
                      Download Excel Workbook
                    </Button>
                    <Button
                      variant="outlined"
                      color="primary"
                      size="large"
                      startIcon={<RefreshIcon />}
                      onClick={handleGenerateAnother}
                      sx={{ py: 1.5, px: 3 }}
                    >
                      Generate Another Report
                    </Button>
                  </Box>
                </CardContent>
              </Card>

              {/* Status Alert if failed */}
              {taskStatus.status === 'failed' && (
                <Alert severity="error" variant="filled" sx={{ borderRadius: 2 }}>
                  <Typography variant="subtitle2" fontWeight={700}>Pipeline Execution Failed</Typography>
                  <Typography variant="body2">{taskStatus.error || 'Detailed error not provided by agent.'}</Typography>
                </Alert>
              )}

              {/* Grid of KPI Metrics */}
              <Grid container spacing={3}>
                
                {/* Duration */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', p: 3 }}>
                      <HourglassEmptyIcon sx={{ fontSize: 32, color: 'secondary.main', mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">Execution Duration</Typography>
                      <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700 }}>
                        {taskStatus.result?.execution_duration || 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Rows Returned */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', p: 3 }}>
                      <TableChartIcon sx={{ fontSize: 32, color: 'secondary.main', mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">Records Returned</Typography>
                      <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700 }}>
                        {taskStatus.result?.records_returned !== undefined ? taskStatus.result.records_returned.toLocaleString() : 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Tables count */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', p: 3 }}>
                      <StorageIcon sx={{ fontSize: 32, color: 'secondary.main', mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">Tables Accessed</Typography>
                      <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700 }}>
                        {taskStatus.result?.tables_used ? taskStatus.result.tables_used.length : 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Generation time */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', p: 3 }}>
                      <TimelineIcon sx={{ fontSize: 32, color: 'secondary.main', mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">Generation Timestamp</Typography>
                      <Typography variant="subtitle1" sx={{ mt: 1, fontWeight: 700 }}>
                        {taskStatus.result?.generation_time || 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                
              </Grid>

              {/* Detailed execution metadata & stages summary */}
              <Grid container spacing={4}>
                
                {/* Tables & Datasets Details */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Typography variant="h6" gutterBottom>Database Context</Typography>
                      <Divider sx={{ mb: 2 }} />
                      
                      <Typography variant="subtitle2" color="text.secondary" mb={0.5}>Datasets Used:</Typography>
                      <Box display="flex" flexWrap="wrap" gap={1} mb={2.5}>
                        {taskStatus.result?.datasets_used && taskStatus.result.datasets_used.length > 0 ? (
                          taskStatus.result.datasets_used.map((ds, idx) => (
                            <Chip key={idx} label={ds} color="primary" size="small" variant="outlined" />
                          ))
                        ) : (
                          <Typography variant="body2" color="text.disabled">None listed</Typography>
                        )}
                      </Box>

                      <Typography variant="subtitle2" color="text.secondary" mb={0.5}>Tables Referenced:</Typography>
                      <Box display="flex" flexWrap="wrap" gap={1}>
                        {taskStatus.result?.tables_used && taskStatus.result.tables_used.length > 0 ? (
                          taskStatus.result.tables_used.map((tbl, idx) => (
                            <Chip key={idx} label={tbl} color="primary" size="small" />
                          ))
                        ) : (
                          <Typography variant="body2" color="text.disabled">None listed</Typography>
                        )}
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Pipeline Services Status */}
                <Grid item xs={12} md={6}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Typography variant="h6" gutterBottom>Universal Catalog Services Audit</Typography>
                      <Divider sx={{ mb: 2 }} />
                      
                      <Box display="flex" flexDirection="column" gap={1.8}>
                        
                        {/* Metadata search */}
                        <Box display="flex" alignItems="center" justifyContent="space-between">
                          <Typography variant="body2" color="text.secondary">Dataplex Metadata Catalog Search</Typography>
                          <Chip 
                            size="small" 
                            label={taskStatus.result?.metadata_search_status || 'Pending'} 
                            color={taskStatus.result?.metadata_search_status === 'Success' ? 'success' : 'default'}
                            icon={taskStatus.result?.metadata_search_status === 'Success' ? <CheckIcon /> : <CancelIcon />}
                          />
                        </Box>

                        {/* Lineage Trace search */}
                        <Box display="flex" alignItems="center" justifyContent="space-between">
                          <Typography variant="body2" color="text.secondary">Dataplex Lineage Mappings Analysis</Typography>
                          <Chip 
                            size="small" 
                            label={taskStatus.result?.lineage_search_status || 'Pending'} 
                            color={taskStatus.result?.lineage_search_status?.includes('Success') ? 'success' : 'default'}
                            icon={taskStatus.result?.lineage_search_status?.includes('Success') ? <CheckIcon /> : <CancelIcon />}
                          />
                        </Box>

                        {/* SQL Compiler */}
                        <Box display="flex" alignItems="center" justifyContent="space-between">
                          <Typography variant="body2" color="text.secondary">SQL Compilation & BQ Dry Run Verification</Typography>
                          <Chip 
                            size="small" 
                            label={taskStatus.result?.sql_execution_status || 'Pending'} 
                            color={taskStatus.result?.sql_execution_status === 'Success' ? 'success' : 'default'}
                            icon={taskStatus.result?.sql_execution_status === 'Success' ? <CheckIcon /> : <CancelIcon />}
                          />
                        </Box>

                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
                
              </Grid>

              {/* REPORT PREVIEW (Only Main_Report Sheet) */}
              <Card>
                <CardContent sx={{ p: 3 }}>
                  <Box display="flex" alignItems="center" gap={1.5} mb={2}>
                    <TableChartIcon sx={{ color: 'primary.main' }} />
                    <Typography variant="h6">Report Preview (Sheet: Main_Report)</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary" mb={2}>
                    Displaying first 100 rows returned from the analytical compiler in real-time.
                  </Typography>
                  
                  <Divider sx={{ mb: 2.5 }} />

                  {loadingPreview ? (
                    <Box display="flex" flexDirection="column" alignItems="center" gap={2} py={6}>
                      <CircularProgress />
                      <Typography variant="body2" color="text.secondary">
                        Loading spreadsheet rows...
                      </Typography>
                    </Box>
                  ) : previewData ? (
                    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 440, borderRadius: 2 }}>
                      <Table stickyHeader size="small">
                        <TableHead>
                          <TableRow>
                            {previewData.columns.map((col, idx) => (
                              <TableCell 
                                key={idx} 
                                align="left"
                                sx={{ 
                                  bgcolor: 'primary.main', 
                                  color: 'white', 
                                  fontWeight: 700,
                                  fontFamily: 'Segoe UI',
                                  fontSize: '0.85rem',
                                  borderRight: '1px solid rgba(255,255,255,0.1)'
                                }}
                              >
                                {col}
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {previewData.data.map((row, rIdx) => (
                            <TableRow 
                              key={rIdx} 
                              hover
                              sx={{ 
                                '&:nth-of-type(even)': { bgcolor: '#f8fafc' }
                              }}
                            >
                              {previewData.columns.map((col, cIdx) => (
                                <TableCell 
                                  key={cIdx} 
                                  align="left"
                                  sx={{ 
                                    fontFamily: 'Segoe UI', 
                                    fontSize: '0.85rem',
                                    borderRight: '1px solid #e2e8f0',
                                    whiteSpace: 'nowrap',
                                    maxWidth: 300,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis'
                                  }}
                                >
                                  {row[col] !== null ? String(row[col]) : <span style={{color: '#94a3b8', fontStyle: 'italic'}}>NULL</span>}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  ) : (
                    <Box py={4} textAlign="center">
                      <Typography variant="body2" color="text.disabled">
                        No preview data available.
                      </Typography>
                    </Box>
                  )}
                </CardContent>
              </Card>

            </Box>
          )}

        </Container>

        {/* Global Notifications Snack */}
        <Snackbar
          open={notification.open}
          autoHideDuration={6000}
          onClose={() => setNotification(prev => ({ ...prev, open: false }))}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert 
            onClose={() => setNotification(prev => ({ ...prev, open: false }))} 
            severity={notification.severity} 
            variant="filled"
            sx={{ width: '100%', borderRadius: 2 }}
          >
            {notification.message}
          </Alert>
        </Snackbar>

      </Box>
    </ThemeProvider>
  );
}
