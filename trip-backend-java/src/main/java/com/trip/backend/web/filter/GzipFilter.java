package com.trip.backend.web.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * GZip Filter（对应 Python GZipMiddleware）
 * - minimum_size=1024
 * - **SSE 响应跳过压缩**（避免缓冲）
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 2)
public class GzipFilter extends OncePerRequestFilter {

    private static final int MIN_GZIP_SIZE = 1024;
    private static final String CONTENT_ENCODING_GZIP = "gzip";
    private static final String RESPONSE_HEADER_CONTENT_ENCODING = "Content-Encoding";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        // 检查是否应该跳过 GZip
        if (shouldSkipGzip(request, response)) {
            filterChain.doFilter(request, response);
            return;
        }

        // 包装 response 以支持 GZip
        GzipResponseWrapper gzipResponse = new GzipResponseWrapper(response);
        try {
            filterChain.doFilter(request, gzipResponse);
        } finally {
            gzipResponse.close();
        }
    }

    /**
     * 判断是否应该跳过 GZip
     */
    private boolean shouldSkipGzip(HttpServletRequest request, HttpServletResponse response) {
        // 1. 检查客户端是否支持 GZip
        String acceptEncoding = request.getHeader("Accept-Encoding");
        if (acceptEncoding == null || !acceptEncoding.contains("gzip")) {
            return true;
        }

        // 2. SSE 响应跳过（避免缓冲）
        String contentType = response.getContentType();
        if (contentType != null && contentType.startsWith("text/event-stream")) {
            return true;
        }

        // 3. 检查响应类型（仅压缩文本类型）
        if (contentType == null) {
            return true; // 未知类型，不压缩
        }

        // 支持的类型
        boolean compressible = contentType.startsWith("text/")
            || contentType.startsWith("application/json")
            || contentType.startsWith("application/javascript")
            || contentType.startsWith("application/xml")
            || contentType.startsWith("application/xhtml+xml");

        return !compressible;
    }

    /**
     * GZip Response Wrapper
     */
    private static class GzipResponseWrapper extends jakarta.servlet.http.HttpServletResponseWrapper {
        private final GzipServletOutputStream gzipOutputStream;
        private final jakarta.servlet.ServletOutputStream originalOutputStream;
        private final java.io.PrintWriter writer;

        GzipResponseWrapper(HttpServletResponse response) throws IOException {
            super(response);
            this.originalOutputStream = response.getOutputStream();
            this.gzipOutputStream = new GzipServletOutputStream(originalOutputStream);
            this.writer = new java.io.PrintWriter(new java.io.OutputStreamWriter(gzipOutputStream, getCharacterEncoding()), true);
        }

        @Override
        public void setContentLength(int len) {
            // 忽略，因为 GZip 后长度会变
        }

        @Override
        public void setHeader(String name, String value) {
            if (RESPONSE_HEADER_CONTENT_ENCODING.equalsIgnoreCase(name)) {
                // 忽略 Content-Encoding，我们自行设置
                return;
            }
            super.setHeader(name, value);
        }

        @Override
        public void addHeader(String name, String value) {
            if (RESPONSE_HEADER_CONTENT_ENCODING.equalsIgnoreCase(name)) {
                return;
            }
            super.addHeader(name, value);
        }

        @Override
        public void setContentType(String type) {
            super.setContentType(type);
        }

        @Override
        public jakarta.servlet.ServletOutputStream getOutputStream() {
            return gzipOutputStream;
        }

        @Override
        public java.io.PrintWriter getWriter() {
            return writer;
        }

        @Override
        public void flushBuffer() throws IOException {
            writer.flush();
            gzipOutputStream.flush();
            super.flushBuffer();
        }

        void close() throws IOException {
            writer.close();
            gzipOutputStream.close();
        }
    }

    /**
     * GZip Servlet Output Stream
     */
    private static class GzipServletOutputStream extends jakarta.servlet.ServletOutputStream {
        private final java.io.OutputStream out;
        private final java.util.zip.GZIPOutputStream gzipStream;
        private boolean closed = false;

        GzipServletOutputStream(java.io.OutputStream out) throws IOException {
            this.out = out;
            this.gzipStream = new java.util.zip.GZIPOutputStream(out);
        }

        @Override
        public void write(int b) throws IOException {
            gzipStream.write(b);
        }

        @Override
        public void write(byte[] b) throws IOException {
            gzipStream.write(b);
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            gzipStream.write(b, off, len);
        }

        @Override
        public void flush() throws IOException {
            gzipStream.flush();
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                gzipStream.finish();
                closed = true;
            }
        }

        @Override
        public boolean isReady() {
            return true;
        }

        @Override
        public void setWriteListener(jakarta.servlet.WriteListener writeListener) {
            // 简单实现
        }
    }
}
