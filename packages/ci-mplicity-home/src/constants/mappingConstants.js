// Quality Score Constants for CIM Field Mapping
export const QUALITY_SCORE_THRESHOLDS = {
    EXCELLENT: { min: 90, color: '#28a745', label: 'Excellent', description: 'Comprehensive CIM compliance' },
    GOOD: { min: 80, color: '#6f9f3e', label: 'Good', description: 'Strong CIM coverage' },
    FAIR: { min: 60, color: '#ffc107', label: 'Fair', description: 'Moderate CIM coverage' },
    POOR: { min: 40, color: '#fd7e14', label: 'Poor', description: 'Limited CIM coverage' },
    CRITICAL: { min: 0, color: '#dc3545', label: 'Critical', description: 'Minimal CIM coverage' }
};

// Get quality score configuration based on percentage
export const getQualityScoreConfig = (percentage) => {
    if (percentage >= QUALITY_SCORE_THRESHOLDS.EXCELLENT.min) return QUALITY_SCORE_THRESHOLDS.EXCELLENT;
    if (percentage >= QUALITY_SCORE_THRESHOLDS.GOOD.min) return QUALITY_SCORE_THRESHOLDS.GOOD;
    if (percentage >= QUALITY_SCORE_THRESHOLDS.FAIR.min) return QUALITY_SCORE_THRESHOLDS.FAIR;
    if (percentage >= QUALITY_SCORE_THRESHOLDS.POOR.min) return QUALITY_SCORE_THRESHOLDS.POOR;
    return QUALITY_SCORE_THRESHOLDS.CRITICAL;
};

// Automatic field mapping patterns for common field names
export const AUTO_MAPPING_PATTERNS = {
    // IP Address patterns
    src_ip: ['src_ip', 'source_ip', 'clientip', 'client_ip', 'remote_addr', 'remote_ip', 'origin_ip'],
    dest_ip: ['dest_ip', 'destination_ip', 'server_ip', 'target_ip', 'host_ip', 'dst_ip'],
    
    // User patterns
    user: ['user', 'username', 'userid', 'user_id', 'login', 'account', 'principal', 'auth'],
    
    // Time patterns
    _time: ['timestamp', 'time', '_time', 'datetime', 'date', 'event_time'],
    
    // Status patterns
    status: ['status', 'response_code', 'http_status', 'result_code', 'exit_code'],
    
    // Action patterns
    action: ['action', 'method', 'http_method', 'verb', 'operation', 'command'],
    
    // Web-specific patterns
    url: ['url', 'uri', 'request_uri', 'path'],
    uri_path: ['uri_path', 'path', 'request_path', 'url_path'],
    http_method: ['method', 'http_method', 'request_method', 'verb'],
    user_agent: ['user_agent', 'useragent', 'ua', 'browser'],
    referer: ['referer', 'referrer', 'ref'],
    
    // Network patterns
    src_port: ['src_port', 'source_port', 'client_port', 'sport'],
    dest_port: ['dest_port', 'destination_port', 'server_port', 'dport', 'port'],
    protocol: ['protocol', 'proto', 'transport'],
    bytes: ['bytes', 'size', 'length', 'content_length'],
    bytes_in: ['bytes_in', 'received_bytes', 'rx_bytes'],
    bytes_out: ['bytes_out', 'sent_bytes', 'tx_bytes'],
    
    // Authentication patterns
    reason: ['reason', 'failure_reason', 'error_reason', 'message'],
    signature: ['signature', 'rule', 'alert', 'event_type'],
    
    // File patterns
    file_name: ['file_name', 'filename', 'file', 'name'],
    file_path: ['file_path', 'filepath', 'path', 'full_path'],
    file_hash: ['file_hash', 'hash', 'md5', 'sha1', 'sha256'],
    
    // Process patterns
    process: ['process', 'process_name', 'proc', 'command'],
    process_path: ['process_path', 'proc_path', 'executable', 'exe'],
    parent_process: ['parent_process', 'parent_proc', 'ppid'],
    
    // Application patterns
    app: ['app', 'application', 'service', 'program'],
    vendor_product: ['vendor_product', 'product', 'vendor', 'tool']
};

// Function to automatically suggest mappings based on field name similarity
export const generateAutoMappings = (extractedFields, cimFields) => {
    const suggestions = {};
    
    cimFields.forEach(cimField => {
        const patterns = AUTO_MAPPING_PATTERNS[cimField] || [];
        const matchedField = extractedFields.find(field => {
            const fieldName = field.name.toLowerCase();
            return patterns.some(pattern => 
                fieldName === pattern.toLowerCase() ||
                fieldName.includes(pattern.toLowerCase()) ||
                pattern.toLowerCase().includes(fieldName)
            );
        });
        
        if (matchedField) {
            suggestions[cimField] = matchedField.name;
        }
    });
    
    return suggestions;
};

// Calculate mapping quality score
export const calculateMappingQuality = (mappings, totalCimFields) => {
    const mappedFields = Object.values(mappings).filter(value => value && value !== '').length;
    return Math.round((mappedFields / totalCimFields) * 100);
}; 