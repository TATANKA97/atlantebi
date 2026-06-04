-- fix_sensitive_semantic_column_tokenization
-- Normalize camelCase names before stripping non-token characters.
with normalized_columns as (
  select
    id,
    lower(
      regexp_replace(
        lower(regexp_replace(physical_name, '([a-z0-9])([A-Z])', '\1 \2', 'g')),
        '[^a-z0-9]+',
        ' ',
        'g'
      )
    ) as token_text
  from public.semantic_columns
),
classified_columns as (
  select
    id,
    case
      when token_text ~ '(^| )(password|passwd|pwd)( |$)' then 'credential'
      when token_text ~ '(^| )(hash|salt)( |$)' then 'credential'
      when token_text ~ '(^| )(secret|token|credential|credentials)( |$)' then 'credential'
      when token_text ~ '(^| )key( |$)'
        and token_text ~ '(^| )(api|access|private|secret)( |$)' then 'credential'
      when token_text ~ '(^| )(email|phone)( |$)' then 'pii'
      when regexp_replace(token_text, '\s+', '', 'g') in (
        'firstname',
        'middlename',
        'lastname',
        'fullname',
        'addressline',
        'addressline1',
        'addressline2'
      ) then 'pii'
      else 'none'
    end as sensitivity_kind,
    case
      when token_text ~ '(^| )(password|passwd|pwd)( |$)' then 'credential_name'
      when token_text ~ '(^| )(hash|salt)( |$)' then 'credential_derivative_name'
      when token_text ~ '(^| )(secret|token|credential|credentials)( |$)' then 'secret_name'
      when token_text ~ '(^| )key( |$)'
        and token_text ~ '(^| )(api|access|private|secret)( |$)' then 'secret_key_name'
      when token_text ~ '(^| )(email|phone)( |$)' then 'contact_identifier'
      when regexp_replace(token_text, '\s+', '', 'g') in (
        'firstname',
        'middlename',
        'lastname',
        'fullname',
        'addressline',
        'addressline1',
        'addressline2'
      ) then 'direct_person_identifier'
      else null
    end as sensitivity_reason
  from normalized_columns
)
update public.semantic_columns as semantic_column
set
  role = case
    when classified_columns.sensitivity_kind = 'credential' then 'unknown'
    else semantic_column.role
  end,
  pii = true,
  metadata = case
    when classified_columns.sensitivity_kind = 'credential' then
      semantic_column.metadata || jsonb_build_object(
        'is_sensitive', true,
        'queryable', false,
        'sensitive_reason', classified_columns.sensitivity_reason
      )
    else
      semantic_column.metadata || jsonb_build_object(
        'pii_reason', classified_columns.sensitivity_reason
      )
  end
from classified_columns
where semantic_column.id = classified_columns.id
  and classified_columns.sensitivity_kind in ('credential', 'pii');
