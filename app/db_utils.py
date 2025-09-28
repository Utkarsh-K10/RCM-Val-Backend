# app/db_utils.py
from sqlalchemy.exc import IntegrityError

def upsert(session, model_instance):
    """
    Insert or update by primary key. Returns the instance.
    Works for single-column primary key (claim_id).
    """
    pk_cols = [c.name for c in model_instance.__table__.primary_key.columns]
    if len(pk_cols) != 1:
        # fallback, just try add
        session.add(model_instance)
        try:
            session.flush()
            return model_instance
        except IntegrityError:
            session.rollback()
            return model_instance
    pk = pk_cols[0]
    pk_value = getattr(model_instance, pk)
    existing = session.get(type(model_instance), pk_value)
    if existing:
        # copy non-pk cols
        for col in model_instance.__table__.columns:
            name = col.name
            if name == pk:
                continue
            setattr(existing, name, getattr(model_instance, name))
        session.add(existing)
        session.flush()
        return existing
    else:
        session.add(model_instance)
        session.flush()
        return model_instance
