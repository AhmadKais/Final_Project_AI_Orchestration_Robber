"""Step-0 hardware/software declaration and its cryptographic signature (Sec. 5.5)."""

from police_thief.shared.system_info import collect_step0_declaration, sign_declaration


def make_declaration():
    return collect_step0_declaration(
        code_version="0.1.0",
        github_commit="deadbeef",
        group_name="test-team",
        sub_game_number=1,
        llm_model="claude-haiku-4-5",
    )


def test_collect_step0_declaration_fills_required_fields():
    declaration = make_declaration()

    assert declaration.os_name  # non-empty on any real machine
    assert declaration.cpu_cores > 0
    assert declaration.llm_model == "claude-haiku-4-5"
    assert declaration.code_version == "0.1.0"
    assert declaration.github_commit == "deadbeef"
    assert declaration.group_name == "test-team"
    assert declaration.sub_game_number == 1


def test_collect_step0_declaration_defaults_repo_and_league_fields_when_omitted():
    declaration = make_declaration()  # no repo_cop/repo_thief/members/games_played_so_far passed
    assert declaration.repo_cop == ""
    assert declaration.repo_thief == ""
    assert declaration.members == ()
    assert declaration.games_played_so_far == 0


def test_collect_step0_declaration_carries_repo_links_and_league_state():
    # Rule 49 ("four links in the JSON of both teams") and Rule 37
    # ("declare precisely the number of games actually played at the start
    # of every game") both need this data to actually travel over Step-0,
    # not just live in local config.
    declaration = collect_step0_declaration(
        code_version="0.1.0", github_commit="deadbeef", group_name="test-team",
        sub_game_number=1, llm_model="claude-haiku-4-5",
        repo_cop="https://github.com/example/cop", repo_thief="https://github.com/example/thief",
        members=["Alice", "Bob"], games_played_so_far=3,
    )
    assert declaration.repo_cop == "https://github.com/example/cop"
    assert declaration.repo_thief == "https://github.com/example/thief"
    assert declaration.members == ("Alice", "Bob")
    assert declaration.games_played_so_far == 3


def test_cpu_freq_and_ram_are_non_negative():
    declaration = make_declaration()
    assert declaration.cpu_freq_mhz >= 0.0
    assert declaration.ram_gb >= 0.0


def test_gpu_absent_is_represented_as_none_not_a_crash():
    declaration = make_declaration()
    # No assumption about whether this test machine has a GPU -- just that
    # the field is well-typed either way (str or None), and vram_gb only
    # set when gpu is.
    assert declaration.gpu is None or isinstance(declaration.gpu, str)
    if declaration.gpu is None:
        assert declaration.vram_gb is None


def test_sign_declaration_is_deterministic_for_same_key():
    declaration = make_declaration()
    key = b"shared-secret-key"

    sig1 = sign_declaration(declaration, key)
    sig2 = sign_declaration(declaration, key)

    assert sig1 == sig2


def test_sign_declaration_differs_with_different_keys():
    declaration = make_declaration()
    sig_a = sign_declaration(declaration, b"key-a")
    sig_b = sign_declaration(declaration, b"key-b")
    assert sig_a != sig_b


def test_sign_declaration_detects_tampering():
    declaration = make_declaration()
    key = b"shared-secret-key"
    original_sig = sign_declaration(declaration, key)

    tampered = collect_step0_declaration(
        code_version="0.1.0",
        github_commit="forged-commit-hash",  # tampered field
        group_name="test-team",
        sub_game_number=1,
        llm_model="claude-haiku-4-5",
    )
    tampered_sig = sign_declaration(tampered, key)

    assert original_sig != tampered_sig
