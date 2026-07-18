FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    # Docling resolves its models from this directory instead of downloading them into
    # a user cache on first use. Baked at build time (see below) so a running container
    # never reaches the network to parse a PDF — ADR-0037's CI-reproducibility objection
    # to docling, answered rather than ignored (ADR-0038).
    DOCLING_ARTIFACTS_PATH=/opt/docling-models

WORKDIR /app

COPY document-intelligence/ /app/

# CPU-only torch first. Docling depends on torch, and the default PyPI wheel drags in the
# full CUDA runtime (several GB of nvidia-* wheels) that this workload can never use.
# Installing the CPU build up front satisfies the dependency before docling is resolved.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
    && pip install --no-cache-dir ".[service]" \
    # docling pulls `opencv-python`, whose cv2 links against X11 libraries
    # (libxcb/libGL) that this slim base does not ship — TableFormer then fails to import
    # at pipeline construction and every PDF silently falls back to the splicing
    # extractor. `opencv-python-headless` is the same cv2 without the GUI bindings, and
    # is both correct and smaller for a server image than installing X11 into it.
    && pip uninstall -y opencv-python \
    && pip install --no-cache-dir opencv-python-headless

# Bake exactly the models this pipeline runs: layout analysis (what keeps the Randtitel
# out of the sentence) and TableFormer. Excluded on purpose:
#   - OCR (rapidocr): disabled in the converter, see ingest/docling_adapter.py. Its opencv
#     dependency needs system libs python:3.12-slim does not ship, and OCR remains
#     deferred — image-only PDFs are flagged `pdf_no_text_layer`, not guessed at.
#   - code/formula and picture-classifier enrichment: off by default, nothing reads them.
RUN python -c "\
from pathlib import Path; \
from docling.utils.model_downloader import download_models; \
download_models(Path('/opt/docling-models'), progress=False, \
    with_layout=True, with_tableformer=True, with_rapidocr=False, \
    with_code_formula=False, with_picture_classifier=False)"

# From here on the image is sealed: any model docling still wants would have to come off
# the network, and this makes that fail loudly at build time instead of in production.
ENV HF_HUB_OFFLINE=1

# Fail the build — not a production request — if the offline model path is incomplete.
COPY document-intelligence/tests/fixtures/zh_as_554_510.pdf /tmp/verify.pdf
RUN python -c "\
from document_intelligence.normalize.pdf import normalize_pdf_document; \
ir = normalize_pdf_document(open('/tmp/verify.pdf','rb').read(), 'build_check'); \
body = ir.body_text; \
assert ir.metadata['pdf_extractor'] == 'docling', ir.metadata; \
assert 'Führung des Hundeverzeichnisses' in body, 'body sentence was spliced'; \
assert 'Führung des Organisation Hundeverzeichnisses' not in body; \
assert ir.metadata['pdf_marginalia']['unmatched'] == [], ir.metadata['pdf_marginalia']; \
print('docling offline PDF normalisation verified:', ir.metadata['pdf_marginalia'])" \
    && rm /tmp/verify.pdf

CMD ["document_intelligence_runtime_ingress"]
