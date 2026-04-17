from app.utils import persona_loader


def test_build_persona_prompt_returns_empty_when_disabled(tmp_path):
    persona_dir = tmp_path / 'persona'
    persona_dir.mkdir()
    (persona_dir / 'soul.md').write_text('Identity block', encoding='utf-8')

    prompt = persona_loader.build_persona_prompt(
        {
            'agent_persona_enabled': False,
            'agent_persona_path': str(persona_dir),
        }
    )

    assert prompt == ''


def test_build_persona_prompt_loads_existing_files_in_expected_order(tmp_path):
    persona_dir = tmp_path / 'persona'
    persona_dir.mkdir()
    (persona_dir / 'operations.md').write_text('Ops', encoding='utf-8')
    (persona_dir / 'soul.md').write_text('Soul', encoding='utf-8')
    (persona_dir / 'style.md').write_text('Style', encoding='utf-8')
    (persona_dir / 'skill.md').write_text('Skill', encoding='utf-8')
    (persona_dir / 'memory.md').write_text('Memory', encoding='utf-8')

    prompt = persona_loader.build_persona_prompt(
        {
            'agent_persona_enabled': True,
            'agent_persona_path': str(persona_dir),
        }
    )

    expected = (
        '<operations>\nOps\n</operations>\n\n'
        '<soul>\nSoul\n</soul>\n\n'
        '<style>\nStyle\n</style>\n\n'
        '<skill>\nSkill\n</skill>\n\n'
        '<memory>\nMemory\n</memory>'
    )
    assert prompt == expected


def test_build_persona_prompt_truncates_large_file(tmp_path):
    persona_dir = tmp_path / 'persona'
    persona_dir.mkdir()
    large = 'A' * (persona_loader._MAX_FILE_CHARS + 100)
    (persona_dir / 'soul.md').write_text(large, encoding='utf-8')

    prompt = persona_loader.build_persona_prompt(
        {
            'agent_persona_enabled': True,
            'agent_persona_path': str(persona_dir),
        }
    )

    assert prompt.startswith('<soul>\n')
    assert prompt.endswith('\n</soul>')
    inner = prompt[len('<soul>\n'):-len('\n</soul>')]
    assert len(inner) == persona_loader._MAX_FILE_CHARS


def test_build_persona_prompt_returns_empty_for_missing_directory(tmp_path):
    missing_dir = tmp_path / 'does-not-exist'

    prompt = persona_loader.build_persona_prompt(
        {
            'agent_persona_enabled': True,
            'agent_persona_path': str(missing_dir),
        }
    )

    assert prompt == ''
