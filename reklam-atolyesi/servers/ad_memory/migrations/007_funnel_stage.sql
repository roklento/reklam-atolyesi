-- 007 (1.9.0): huni aşamasına göre içerik planlama. Yalnızca sütun ekler (CHECK değişmez, tablo yeniden kurulmaz).
-- Ürünün satın alma engelleri (S00c): [{code, text, source, answer?, evidence?: {kind, ref}}]; cevabın kanıtı yoksa BOFU'da cevaplanmaz.
ALTER TABLE products ADD COLUMN objections_json TEXT;
-- Konseptin mesaj kartı (S03): {stage, stage_basis, stage_basis_note?, belief, focus, objection_code?, evidence: [{kind, ref}], expected_action}.
ALTER TABLE concepts ADD COLUMN message_json TEXT;
-- Aşama teşhis metrikleri (Meta: landing_page_view, omni_view_content, omni_initiated_checkout; canlı ads_get_field_context 2026-10-29).
ALTER TABLE metrics_daily ADD COLUMN landing_page_views INTEGER;
ALTER TABLE metrics_daily ADD COLUMN view_content INTEGER;
ALTER TABLE metrics_daily ADD COLUMN initiate_checkout INTEGER;
