package routes

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"jsonify2ai/api/internal/config"

	"github.com/gin-gonic/gin"
)

type askRequest struct {
	Kind  string `json:"kind"`
	Q     string `json:"q"`
	Limit int    `json:"limit"`
}

type searchResult struct {
	Text       string  `json:"text"`
	Score      float64 `json:"score"`
	DocumentID string  `json:"document_id"`
	Path       string  `json:"path"`
	ChunkIndex *int    `json:"chunk_index,omitempty"`
	Meta       any     `json:"meta,omitempty"`
}

type askResponse struct {
	Ok       bool           `json:"ok"`
	Question string         `json:"question"`
	Answers  []searchResult `json:"answers"`
}

// Register this in server: r.POST("/ask", (&AskHandler{}).Post)
type AskHandler struct {
	Config *config.Config
}

func (h *AskHandler) workerBaseURL() string {
	wb := h.Config.WorkerBase
	if wb == "" {
		wb = "http://worker:8090"
	}
	return wb
}

func (h *AskHandler) Post(c *gin.Context) {
	var req askRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "bad_request", "detail": err.Error()})
		return
	}
	if req.Kind == "" {
		req.Kind = "text"
	}
	if req.Limit <= 0 || req.Limit > 10 {
		req.Limit = 3
	}

	// Extract optional query params for filters
	documentID := c.Query("document_id")
	pathPrefix := c.Query("path_prefix")

	// Primary path: call worker /ask with {query, kind, limit, document_id?, path_prefix?}
	wreq := map[string]any{
		"query": req.Q,
		"kind":  req.Kind,
		"limit": req.Limit,
	}
	if documentID != "" {
		wreq["document_id"] = documentID
	}
	if pathPrefix != "" {
		wreq["path_prefix"] = pathPrefix
	}
	wbody, _ := json.Marshal(wreq)
	wurl := fmt.Sprintf("%s/ask", h.workerBaseURL())
	httpClient := &http.Client{Timeout: 60 * time.Second}

	fwd, err := http.NewRequest(http.MethodPost, wurl, bytes.NewReader(wbody))
	if err == nil {
		// propagate Request-ID if any
		if rid := c.GetHeader("X-Request-Id"); rid != "" {
			fwd.Header.Set("X-Request-Id", rid)
		}
		fwd.Header.Set("Content-Type", "application/json")
		if resp, err := httpClient.Do(fwd); err == nil {
			defer resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				// pass through worker /ask JSON
				c.Status(resp.StatusCode)
				io.Copy(c.Writer, resp.Body)
				return
			}
		}
	}

	// Fallback: worker /search -> map to answers
	// GET /search?kind=&q=&limit=&document_id=&path=
	sURL := fmt.Sprintf("%s/search?kind=%s&q=%s&limit=%d", h.workerBaseURL(), req.Kind, urlQueryEscape(req.Q), req.Limit)
	if documentID != "" {
		sURL += "&document_id=" + urlQueryEscape(documentID)
	}
	if pathPrefix != "" {
		sURL += "&path=" + urlQueryEscape(pathPrefix)
	}
	sreq, _ := http.NewRequest(http.MethodGet, sURL, nil)
	if rid := c.GetHeader("X-Request-Id"); rid != "" {
		sreq.Header.Set("X-Request-Id", rid)
	}
	sresp, serr := httpClient.Do(sreq)
	if serr != nil {
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker_unreachable", "detail": serr.Error()})
		return
	}
	defer sresp.Body.Close()
	if sresp.StatusCode < 200 || sresp.StatusCode >= 300 {
		// bubble up as 502 with worker response text
		body, _ := io.ReadAll(sresp.Body)
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker_search_failed", "detail": string(body)})
		return
	}
	var sjson struct {
		Ok      bool           `json:"ok"`
		Results []searchResult `json:"results"`
	}
	if err := json.NewDecoder(sresp.Body).Decode(&sjson); err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "decode_error", "detail": err.Error()})
		return
	}
	out := askResponse{Ok: true, Question: req.Q}
	if len(sjson.Results) > 0 {
		// keep top N as answers
		n := req.Limit
		if n > len(sjson.Results) {
			n = len(sjson.Results)
		}
		out.Answers = sjson.Results[:n]
	} else {
		out.Answers = []searchResult{}
	}
	c.JSON(http.StatusOK, out)
}

// helper for safe query escaping without importing net/url in many places
func urlQueryEscape(s string) string {
	// minimal wrapper; ok for typical ASCII questions
	return url.QueryEscape(s)
}
