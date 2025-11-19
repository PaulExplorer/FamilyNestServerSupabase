CREATE OR REPLACE FUNCTION batch_update_persons_atomic(
    p_tree_id UUID,
    p_persons_to_add JSONB,
    p_persons_to_modify JSONB,
    p_ids_to_delete INT[]
)
RETURNS VOID AS $$
DECLARE
    person_to_modify JSONB;
    person_id INT;
    expected_version INT;
    current_version INT;
    new_data JSONB;
    v_has_changes BOOLEAN := false;
BEGIN
    -- 1. Check versions for all persons to modify BEFORE any writing.
    -- The FOR loop over a JSONB array iterates over each object.
    IF p_persons_to_modify IS NOT NULL THEN
        FOR person_to_modify IN SELECT * FROM jsonb_array_elements(p_persons_to_modify)
        LOOP
            person_id := (person_to_modify->>'id')::INT;
            expected_version := (person_to_modify->>'version')::INT;

            -- Raise an exception if the version is missing.
            IF expected_version IS NULL THEN
                RAISE EXCEPTION 'Missing version for person ID %', person_id;
            END IF;

            -- Lock the row for checking and future update (FOR UPDATE)
            -- and retrieve the current version.
            SELECT (data->>'version')::INT INTO current_version
            FROM public.persons
            WHERE id = person_id AND tree_id = p_tree_id
            FOR UPDATE;

            -- If the person is not found, `current_version` will be NULL.
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Person not found: ID %', person_id;
            END IF;

            -- Compare versions.
            IF current_version IS NULL OR current_version != expected_version THEN
                RAISE EXCEPTION 'Version conflict for person ID %: expected %, found %', person_id, expected_version, current_version;
            END IF;
        END LOOP;
    END IF;

    -- If all checks above succeed, we can proceed with modifications.
    -- If an exception was raised, the function stops here and nothing is modified.

    -- 2. Delete persons
    IF array_length(p_ids_to_delete, 1) > 0 THEN
        DELETE FROM public.persons
        WHERE tree_id = p_tree_id AND id = ANY(p_ids_to_delete);
        v_has_changes := true;
    END IF;

    -- 3. Modify persons
    IF p_persons_to_modify IS NOT NULL THEN
        FOR person_to_modify IN SELECT * FROM jsonb_array_elements(p_persons_to_modify)
        LOOP
            person_id := (person_to_modify->>'id')::INT;
            current_version := (person_to_modify->>'version')::INT;

            -- Prepare new data by incrementing the version
            new_data := jsonb_set(
                person_to_modify,
                '{version}',
                (current_version + 1)::TEXT::JSONB
            );

            UPDATE public.persons
            SET data = new_data
            WHERE id = person_id AND tree_id = p_tree_id;
            v_has_changes := true;
        END LOOP;
    END IF;

    -- 4. Add new persons
    IF p_persons_to_add IS NOT NULL AND jsonb_array_length(p_persons_to_add) > 0 THEN
        INSERT INTO public.persons (id, tree_id, data)
        SELECT
            (p->>'id')::INT,
            p_tree_id,
            jsonb_set(p, '{version}', '0'::JSONB) -- Initialize version to 0
        FROM jsonb_array_elements(p_persons_to_add) AS p;
        v_has_changes := true;
    END IF;

    -- 5. Update the tree modification date if any changes occurred
    IF v_has_changes THEN
        UPDATE public.trees
        SET updated_at = now()
        WHERE id = p_tree_id;
    END IF;

END;
$$ LANGUAGE plpgsql;
