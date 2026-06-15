# MeetTrack RAG API

Uso para probar conexiones, indexar datos, sincronizar información y consultar el sistema RAG usando los endpoints disponibles.

---

* [1. Probar conexiones](#1-probar-conexiones)
* [2. Indexar datos por primera vez](#2-indexar-datos-por-primera-vez)
* [3. Sincronizar datos](#3-sincronizar-datos)
* [4. Consultar al RAG](#4-consultar-al-rag)
* [5. Uso de memoria conversacional](#5-uso-de-memoria-conversacional)
* [6. Flujo recomendado](#6-flujo-recomendado)

---

## 1. Probar conexiones

Antes de ejecutar consultas RAG, valida que las conexiones principales estén funcionando correctamente.

Este endpoint verifica:

* Conexión con MeetTrack
* Configuración del proveedor LLM
* Configuración del proveedor de embeddings
* Conexión con SQL Server

### Endpoint

```http
GET /api/rag/debug/connections
```

### Respuesta esperada

```json
{
  "meettrack": {
    "status": "ok",
    "totalRecords": 30,
    "has_data": true
  },
  "openai": {
    "status": "ok",
    "llm_provider": "farm",
    "embedding_provider": "local",
    "chat_model": "askbosch-prod-farm-openai-gpt-4o-mini-2024-07-18",
    "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "proxy_used": "http://127.0.0.1:3128",
    "verify_ssl": true,
    "ca_bundle": null,
    "embeddings": {
      "status": "ok",
      "provider": "local",
      "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "embedding_dimensions": 384
    },
    "chat": {
      "status": "ok",
      "provider": "farm",
      "model": "askbosch-prod-farm-openai-gpt-4o-mini-2024-07-18",
      "response_preview": "ok"
    }
  },
  "sql_server": {
    "status": "ok",
    "result": 1
  }
}
```

### Validaciones

La respuesta debe confirmar que:

| Servicio      | Validación esperada                      |
| ------------- | ---------------------------------------- |
| MeetTrack     | `meettrack.status` debe ser `ok`         |
| MeetTrack     | `meettrack.has_data` debe ser `true`     |
| OpenAI / FARM | `openai.status` debe ser `ok`            |
| Embeddings    | `openai.embeddings.status` debe ser `ok` |
| Chat          | `openai.chat.status` debe ser `ok`       |
| SQL Server    | `sql_server.status` debe ser `ok`        |

---

## 2. Indexar datos por primera vez

Este endpoint sirve para llenar Chroma con los documentos procesados desde MeetTrack.

Debe ejecutarse después de confirmar que las conexiones están funcionando correctamente.

### Endpoint

```http
POST /api/rag/ingest
```

### Parámetros

| Parámetro    | Tipo              | Ejemplo      | Descripción                          |
| ------------ | ----------------- | ------------ | ------------------------------------ |
| `start_date` | `string` o `null` | `2026-01-01` | Fecha inicial para filtrar reuniones |
| `end_date`   | `string` o `null` | `2026-06-30` | Fecha final para filtrar reuniones   |


### Ejemplo de request

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-06-30"
}
```

### Respuesta esperada

```json
{
  "success": true,
  "total_records_from_api": 30,
  "total_meetings_filtered": 30,
  "total_documents_indexed": 165,
  "total_collections_used": 4,
  "collections_used": [
    "meettrack_rag_2026_02",
    "meettrack_rag_2026_03",
    "meettrack_rag_2026_04",
    "meettrack_rag_2026_05"
  ],
  "filter_applied": true,
  "filter_start_date": "2026-01-01",
  "filter_end_date": "2026-06-30",
  "date_scope": "meeting",
  "message": "Ingest completed in Chroma using month-year collections."
}
```

---

## 3. Sincronizar datos

Este endpoint se usa cuando MeetTrack ya tiene datos nuevos o modificados.

A diferencia de `/api/rag/ingest`, este endpoint está pensado para refrescar documentos existentes o agregar información nueva sin rehacer todo el proceso inicial.

### Endpoint

```http
POST /api/rag/sync
```

### Parámetros

| Parámetro    | Tipo              | Ejemplo      | Descripción                              |
| ------------ | ----------------- | ------------ | ---------------------------------------- |
| `start_date` | `string` o `null` | `2026-06-01` | Fecha inicial para sincronizar reuniones |
| `end_date`   | `string` o `null` | `2026-06-30` | Fecha final para sincronizar reuniones   |

### Ejemplo de request

```json
{
  "start_date": "2026-06-01",
  "end_date": "2026-06-30"
}
```

### Respuesta esperada

```json
{
  "success": true,
  "total_records_from_api": 30,
  "total_meetings_filtered": 0,
  "total_documents_found": 0,
  "new_documents": 0,
  "updated_documents": 0,
  "unchanged_documents": 0,
  "total_collections_used": 0,
  "collections_used": [],
  "filter_applied": true,
  "filter_start_date": "2026-06-01",
  "filter_end_date": "2026-06-30",
  "date_scope": "meeting",
  "message": "Sync completed. Existing documents for the affected meetings were refreshed."
}
```

---

## 4. Consultar al RAG

Después de indexar o sincronizar los datos, puedes consultar al RAG usando los endpoints de preguntas.

### Endpoints disponibles

| Endpoint            | Método | Descripción                                       |
| ------------------- | -----: | ------------------------------------------------- |
| `/api/rag/ask`      | `POST` | Pregunta al RAG y devuelve respuesta con fuentes  |
| `/api/rag/ask-text` | `POST` | Pregunta al RAG y devuelve solo texto en Markdown |

---

### 4.1 Consulta con respuesta y fuentes

```http
POST /api/rag/ask
```

### Ejemplo de request

```json
{
  "username_fk": "emmanuel",
  "question": "¿Qué pasó en febrero 2026?",
  "top_k": 10,
  "mode": "auto"
}
```

### Campos principales

| Campo         | Tipo     | Descripción                                          |
| ------------- | -------- | ---------------------------------------------------- |
| `username_fk` | `string` | Usuario que realiza la consulta                      |
| `question`    | `string` | Pregunta enviada al RAG                              |
| `top_k`       | `number` | Cantidad máxima de documentos relevantes a recuperar |
| `mode`        | `string` | Modo de búsqueda o respuesta. Ejemplo: `auto`        |

---

### 4.2 Consulta con respuesta Markdown

```http
POST /api/rag/ask-text
```

Este endpoint devuelve únicamente la respuesta en formato texto/Markdown, sin estructura completa de fuentes.

### Ejemplo de request

```json
{
  "username_fk": "emmanuel",
  "question": "¿Qué pasó en febrero 2026?",
  "top_k": 10,
  "mode": "auto"
}
```

---

## 5. Uso de memoria conversacional

Puedes activar memoria conversacional enviando los campos relacionados con historial.

Esto permite que el RAG tome en cuenta mensajes recientes de una conversación previa.

### Consulta sin memoria

```json
{
  "username_fk": "emmanuel",
  "question": "¿Qué pasó en febrero 2026?",
  "top_k": 10,
  "mode": "auto"
}
```

### Consulta con memoria

```json
{
  "username_fk": "emmanuel",
  "question": "hola",
  "top_k": 10,
  "mode": "auto",
  "context_history_id": 2,
  "include_recent_history": true,
  "history_limit": 6
}
```

### Campos de memoria

| Campo                    | Tipo      | Descripción                                                   |
| ------------------------ | --------- | ------------------------------------------------------------- |
| `context_history_id`     | `number`  | ID del historial conversacional que se quiere usar            |
| `include_recent_history` | `boolean` | Activa o desactiva el uso de memoria reciente                 |
| `history_limit`          | `number`  | Cantidad máxima de mensajes recientes a incluir como contexto |

### Switch recomendado para memoria

Puedes manejar la memoria desde frontend o backend con un switch:

```json
{
  "include_recent_history": true
}
```

Cuando el switch esté activo, se envían también:

```json
{
  "context_history_id": 2,
  "history_limit": 6
}
```

Cuando esté apagado, esos campos pueden omitirse.

---