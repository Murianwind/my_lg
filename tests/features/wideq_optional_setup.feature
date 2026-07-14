# -*- coding: utf-8 -*-
Feature: wideq 연결 실패 시에도 PAT만으로 통합구성요소가 살아남는다
  wideq 서버가 불안정하거나 약관 동의가 필요해서 연결에 실패해도,
  PAT 기반 기능(전원/모드/온도/습도)은 계속 제공되어야 하고 통합
  구성요소 전체가 죽으면 안 된다. 반대로 wideq가 다시 연결 가능해지면
  자동으로 재연결을 시도하고 통합구성요소를 재로드해야 한다.

  Scenario: wideq도 PAT도 모두 정상이면 설정이 성공한다
    When wideq 연결 성공, PAT 기기 조회 성공 상태로 통합구성요소를 설정한다
    Then 설정은 예외 없이 성공해야 한다

  Scenario: wideq 연결에 실패해도 PAT 조회가 성공하면 설정은 계속된다
    When wideq 연결 실패, PAT 기기 조회 성공 상태로 통합구성요소를 설정한다
    Then 설정은 예외 없이 성공해야 한다

  Scenario: wideq도 실패하고 PAT 조회도 실패하면 ConfigEntryNotReady여야 한다
    When wideq 연결 실패, PAT 기기 조회 실패 상태로 통합구성요소를 설정한다
    Then 예외는 ConfigEntryNotReady 이어야 한다

  Scenario: wideq가 다시 연결되면 통합구성요소가 자동으로 재로드된다
    When wideq가 다시 연결 가능해진 상태에서 주기적 재연결 작업이 실행된다
    Then 통합구성요소 재로드가 호출되어야 한다
